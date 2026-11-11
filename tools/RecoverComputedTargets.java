// Recover inline computed-jump destinations in the special-stage renderer.
import ghidra.app.script.GhidraScript;
public class RecoverComputedTargets extends GhidraScript {
    @Override public void run() throws Exception {
        for (long table : new long[] {0x49a878L, 0x49a980L}) {
            int count = table == 0x49a878L ? 66 : 5;
            for (int index = 0; index < count; index++) {
                long target = Integer.toUnsignedLong(getInt(toAddr(table + index * 4)));
                if (target < 0x410000L || target >= 0x4ae400L)
                    throw new Exception("Invalid computed destination " + Long.toHexString(target));
                disassemble(toAddr(target));
                println("Computed destination " + Long.toHexString(target));
            }
        }
    }
}
