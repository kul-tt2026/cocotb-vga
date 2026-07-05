# Runs the cocotb-vga self-test: captures frames from the bundled dummy VGA
# pattern generator and checks them pixel-exactly against the expected image.
#
#   make                          # fast 64x48 'toy' mode (~seconds)
#   make VGA_SELFTEST_TIMING=vga  # one full 640x480@60 frame (~minutes)
#
# Requires cocotb-vga to be installed (pip install -e ..).

SIM ?= icarus
TOPLEVEL_LANG ?= verilog

VGA_SELFTEST_TIMING ?= toy
export VGA_SELFTEST_TIMING

PYTHON3 ?= python3
COCOTB_VGA_VERILOG := $(shell $(PYTHON3) -c "import cocotb_vga; print(cocotb_vga.verilog_dir())")

VERILOG_SOURCES = $(COCOTB_VGA_VERILOG)/dummy_vga.v
COCOTB_TOPLEVEL = dummy_vga
COCOTB_TEST_MODULES = cocotb_vga.selftest

# The 'toy' geometry must match cocotb_vga.timing.TOY_64x48.
ifeq ($(VGA_SELFTEST_TIMING),toy)
COMPILE_ARGS += -Pdummy_vga.H_ACTIVE=64 -Pdummy_vga.H_FRONT=2 -Pdummy_vga.H_SYNC=4 -Pdummy_vga.H_BACK=6
COMPILE_ARGS += -Pdummy_vga.V_ACTIVE=48 -Pdummy_vga.V_FRONT=2 -Pdummy_vga.V_SYNC=2 -Pdummy_vga.V_BACK=3
endif

include $(shell cocotb-config --makefiles)/Makefile.sim

.PHONY: clean
clean::
	rm -rf sim_build __pycache__ results.xml vga_out
