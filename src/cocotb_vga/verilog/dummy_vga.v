`default_nettype none
`timescale 1ns / 1ps

// Testbench-only VGA pattern generator used to validate the cocotb-vga
// capture library (not meant for synthesis: it uses a division).
//
// Pattern: 8 vertical color bars, 2 bits per channel, shifting one bar
// position every frame. Must be kept in sync with cocotb_vga/pattern.py.
//
// Outputs are exposed both as individual signals (hsync/vsync/r/g/b) and
// packed in the Tiny Tapeout TinyVGA Pmod pinout (uo_out).
module dummy_vga #(
    parameter H_ACTIVE = 640,
    parameter H_FRONT  = 16,
    parameter H_SYNC   = 96,
    parameter H_BACK   = 48,
    parameter V_ACTIVE = 480,
    parameter V_FRONT  = 10,
    parameter V_SYNC   = 2,
    parameter V_BACK   = 33,
    parameter [0:0] HS_ACTIVE = 1'b0,  // asserted sync level
    parameter [0:0] VS_ACTIVE = 1'b0,
    parameter REGISTER_OUTPUTS = 1
) (
    input  wire       clk,
    input  wire       rst_n,
    output wire       hsync,
    output wire       vsync,
    output wire [1:0] r,
    output wire [1:0] g,
    output wire [1:0] b,
    output wire [7:0] uo_out
);

  localparam H_TOTAL = H_ACTIVE + H_FRONT + H_SYNC + H_BACK;
  localparam V_TOTAL = V_ACTIVE + V_FRONT + V_SYNC + V_BACK;

  reg [15:0] hcnt;
  reg [15:0] vcnt;
  reg [7:0]  frame_cnt;

  always @(posedge clk) begin
    if (!rst_n) begin
      hcnt      <= 0;
      vcnt      <= 0;
      frame_cnt <= 0;
    end else if (hcnt == H_TOTAL - 1) begin
      hcnt <= 0;
      if (vcnt == V_TOTAL - 1) begin
        vcnt      <= 0;
        frame_cnt <= frame_cnt + 1;
      end else begin
        vcnt <= vcnt + 1;
      end
    end else begin
      hcnt <= hcnt + 1;
    end
  end

  wire active = (hcnt < H_ACTIVE) && (vcnt < V_ACTIVE);
  wire hs_w = ((hcnt >= H_ACTIVE + H_FRONT) && (hcnt < H_ACTIVE + H_FRONT + H_SYNC))
              ? HS_ACTIVE : ~HS_ACTIVE;
  wire vs_w = ((vcnt >= V_ACTIVE + V_FRONT) && (vcnt < V_ACTIVE + V_FRONT + V_SYNC))
              ? VS_ACTIVE : ~VS_ACTIVE;

  wire [15:0] bar = (hcnt << 3) / H_ACTIVE + {8'd0, frame_cnt};
  reg [5:0] rgb_w;  // {r[1:0], g[1:0], b[1:0]}
  always @* begin
    if (!active) rgb_w = 6'b00_00_00;
    else
      case (bar[2:0])
        3'd0: rgb_w = 6'b11_11_11;  // white
        3'd1: rgb_w = 6'b11_11_00;  // yellow
        3'd2: rgb_w = 6'b00_11_11;  // cyan
        3'd3: rgb_w = 6'b00_11_00;  // green
        3'd4: rgb_w = 6'b11_00_11;  // magenta
        3'd5: rgb_w = 6'b11_00_00;  // red
        3'd6: rgb_w = 6'b00_00_11;  // blue
        default: rgb_w = 6'b00_01_01;  // dark teal (distinguishable from blanking)
      endcase
  end

  generate
    if (REGISTER_OUTPUTS) begin : g_reg
      reg hs_q, vs_q;
      reg [5:0] rgb_q;
      always @(posedge clk) begin
        hs_q  <= hs_w;
        vs_q  <= vs_w;
        rgb_q <= rgb_w;
      end
      assign hsync = hs_q;
      assign vsync = vs_q;
      assign {r, g, b} = rgb_q;
    end else begin : g_comb
      assign hsync = hs_w;
      assign vsync = vs_w;
      assign {r, g, b} = rgb_w;
    end
  endgenerate

  // TinyVGA Pmod pinout (https://github.com/mole99/tiny-vga):
  // uo_out[0]=R1 [1]=G1 [2]=B1 [3]=VS [4]=R0 [5]=G0 [6]=B0 [7]=HS
  assign uo_out = {hsync, b[0], g[0], r[0], vsync, b[1], g[1], r[1]};

endmodule
