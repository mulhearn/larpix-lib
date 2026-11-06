# larpix/asic/asic_config.py

from typing import Any
from larpix_control.common.interfaces import AsicConfigIface, AsicRegisterIface, RegisterOp

from .asic_spec import AsicSpec
from . import _fragment as _frag

class AsicConfig(AsicConfigIface):
    """ASIC configuration through fragments, written as register ops on one io channel.

    Requires an AsicSpec instance and a collapsed fragment library
    at initialization.
    """

    def __init__(self, reg_io: AsicRegisterIface, spec: AsicSpec, frag_lib: dict[str, dict],
                 io_chan: int, verbose: bool = False):
        """
        Parameters:
            reg_io: register access to the ASICs
            spec: an instance of AsicSpec representing the hardware
            frag_lib: dict of collapsed fragments, keyed by name
            io_chan: the io channel of the chips configured
            verbose: optional flag for printing progress
        """
        self.reg_io = reg_io
        self.io_chan = io_chan
        self.spec = spec
        self.frag_lib = frag_lib
        self.verbose = verbose

        if verbose:
            spec_name = spec.name()
            print(f"AsicConfig initialized with spec {spec_name} and {len(frag_lib)} fragments")

    def write_fields(self, chip_id: int, update: dict) -> None:
        """Write the registers holding the field updates to chip_id."""
        ops = [RegisterOp.write(self.io_chan, chip_id, reg, value)
               for reg, value in self.spec.build_write_list(update=update)]
        for op in ops if self.verbose else []:
            print(f"#TRACE I/O:  chan 0x{op.io_chan:X} chip {op.chip} reg {op.reg} = 0x{op.value:02X}")
        replies = self.reg_io.transmit(ops, fire_and_forget=True)
        if not replies.complete:
            print(f"WARNING:  chip {chip_id}:  writes not all acknowledged")

    def list_fragments(self):
        print("available fragments:")
        for name in self.frag_lib:
            print(f"  {name}")

    def set_chip_id(self, chip_id: int):
        if self.verbose:
            print(f"INFO: initializing new chip with chip_id {chip_id}")
        external = { "chip_id": chip_id }
        evaluated = _frag.evaluate_collapsed(self.frag_lib["set_chip_id"], external, verbose=self.verbose)
        if self.verbose:
            _frag.print_evaluated(evaluated)
        #chip_id is 1 after reset:
        self.write_fields(1, evaluated)

    def init_root_chip_io(self, chip_id: int, fpga_port: str) -> None:
        if self.verbose:
            print(f"init_root_chip_io called with chip_id={chip_id}, fpga_port={fpga_port}")
        fpga = self.spec.input_index(fpga_port)
        external = { "fpga": [fpga] }
        evaluated = _frag.evaluate_collapsed(self.frag_lib["init_rx_root_chip"], external, verbose=self.verbose)
        if self.verbose:
            print("INFO:  evaluated init_rx_root_chip fragment:")
            _frag.print_evaluated(evaluated)
        self.write_fields(chip_id, evaluated)
        self.init_io(chip_id)

    def init_io(self, chip_id: int) -> None:
        if self.verbose:
            print(f"init_io called with chip_id={chip_id}")
        init_rx = self.frag_lib["init_rx"];
        init_tx = self.frag_lib["init_tx"];
        rxtx = _frag.merge_fragments([init_rx, init_tx])
        evaluated = _frag.evaluate_collapsed(rxtx, [], verbose=self.verbose)
        if self.verbose:
            _frag.print_evaluated(evaluated)
        self.write_fields(chip_id, evaluated)

    def set_input_enables(self, chip_id: int, ports: list[str]) -> None:
        port_idxs = self.spec.input_indices(ports)
        if self.verbose:
            print(f"set_input_enables called with chip_id={chip_id}, ports={ports}")
            print(f"   port indices: {port_idxs}")
        frag = self.frag_lib["set_input"]
        external = { "input": port_idxs }
        evaluated = _frag.evaluate_collapsed(frag, external, verbose=self.verbose)
        if self.verbose:
            _frag.print_evaluated(evaluated)
        self.write_fields(chip_id, evaluated)

    def set_downstream_output_enables(self, chip_id: int, ports: list[str]) -> None:
        port_idxs = self.spec.output_indices(ports)
        if self.verbose:
            print(f"set_downstream_output_enables called with chip_id={chip_id}, ports={ports}")
            print(f"   port indices: {port_idxs}")
        external = { "downstream": port_idxs }
        frag = self.frag_lib["set_downstream"]
        evaluated = _frag.evaluate_collapsed(frag, external, verbose=self.verbose)
        if self.verbose:
            _frag.print_evaluated(evaluated)
        self.write_fields(chip_id, evaluated)

    def set_upstream_output_enables(self, chip_id: int, ports: list[str]) -> None:
        port_idxs = self.spec.output_indices(ports)
        if self.verbose:
            print(f"set_upstream_output_enables called with chip_id={chip_id}, ports={ports}")
            print(f"   port indices: {port_idxs}")
        external = { "upstream": port_idxs }
        frag = self.frag_lib["set_upstream"]
        evaluated = _frag.evaluate_collapsed(frag, external, verbose=self.verbose)
        if self.verbose:
            _frag.print_evaluated(evaluated)
        self.write_fields(chip_id, evaluated)
