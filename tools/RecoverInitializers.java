// Watcom's initializer table contains function pointers the PE analyzer missed.
import ghidra.app.script.GhidraScript;
public class RecoverInitializers extends GhidraScript {
    @Override public void run() throws Exception {
        for (long address : new long[] {0x41d880L, 0x41d890L, 0x41d8a0L, 0x41d8b0L, 0x41d8c0L,
                0x41d8d0L, 0x41d8e0L, 0x47d980L, 0x489110L, 0x49f1f0L}) {
            disassemble(toAddr(address));
            if (getFunctionAt(toAddr(address)) == null)
                createFunction(toAddr(address), null);
            println("Recovered initializer " + Long.toHexString(address));
        }
    }
}
