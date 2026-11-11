// Export Ghidra's raw instruction semantics for native recompilation.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.lang.*;
import ghidra.program.model.pcode.*;
import ghidra.program.model.address.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;

public class ExportPcode extends GhidraScript {
    private String q(String s) {
        return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + "\"";
    }
    private String vn(Varnode v) {
        if (v == null) return "null";
        Address a = v.getAddress();
        String kind = v.isConstant() ? "c" : v.isRegister() ? "r" : v.isUnique() ? "u" : a.getAddressSpace().isMemorySpace() ? "m" : a.getAddressSpace().getName();
        return "[" + q(kind) + "," + Long.toUnsignedString(v.getOffset()) + "," + v.getSize() + "]";
    }
    @Override public void run() throws Exception {
        Path out = Paths.get(getScriptArgs()[0]);
        Files.createDirectories(out);
        PrintWriter regs = new PrintWriter(Files.newBufferedWriter(out.resolve("registers.tsv")));
        for (Register r : currentProgram.getLanguage().getRegisters()) {
            regs.println(r.getName() + "\t" + r.getAddress().getOffset() + "\t" + r.getNumBytes() + "\t" + r.getLeastSignificantBit());
        }
        regs.close();
        PrintWriter userops = new PrintWriter(Files.newBufferedWriter(out.resolve("userops.tsv")));
        Language language = currentProgram.getLanguage();
        for (int j = 0; j < language.getNumberOfUserDefinedOpNames(); j++) userops.println(j + "\t" + language.getUserDefinedOpName(j));
        userops.close();
        PrintWriter code = new PrintWriter(Files.newBufferedWriter(out.resolve("instructions.jsonl")));
        int n = 0;
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Instruction ins = it.next();
            if (!ins.getAddress().isMemoryAddress()) continue;
            long a = ins.getAddress().getOffset();
            if (a < 0x410000 || a >= 0x4ae400) continue;
            StringBuilder b = new StringBuilder();
            b.append("{\"a\":").append(a).append(",\"n\":").append(ins.getLength()).append(",\"s\":").append(q(ins.toString())).append(",\"ops\":[");
            boolean comma = false;
            for (PcodeOp op : ins.getPcode()) {
                if (comma) b.append(','); comma = true;
                b.append('[').append(q(op.getMnemonic())).append(',').append(vn(op.getOutput()));
                for (Varnode v : op.getInputs()) b.append(',').append(vn(v));
                b.append(']');
            }
            b.append("]}");
            code.println(b.toString());
            n++;
        }
        code.close();
        println("Exported " + n + " instructions");
    }
}
