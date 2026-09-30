package com.demandhub.agent.llm;

/**
 * Mock 向量（一期）：字符二元组哈希 → 128 维计数向量 → L2 归一化。
 * 确定性输出，无需外部服务；二期替换为大模型平台 embedding 时仅改 LlmClient.embed 实现，
 * knowledge_doc.embedding 列（JSON）与检索接口保持不变。
 */
public final class MockEmbedding {

    public static final int DIM = 128;

    private MockEmbedding() {
    }

    public static double[] embed(String text) {
        double[] vec = new double[DIM];
        if (text == null || text.isBlank()) {
            return vec;
        }
        String t = text.replaceAll("\\s+", "");
        for (int i = 0; i < t.length() - 1; i++) {
            int bucket = Math.floorMod(t.substring(i, i + 2).hashCode(), DIM);
            vec[bucket] += 1.0;
        }
        // 单字兜底，避免两字以下的文本得到零向量
        if (t.length() == 1) {
            vec[Math.floorMod(t.hashCode(), DIM)] += 1.0;
        }
        double norm = 0;
        for (double v : vec) {
            norm += v * v;
        }
        norm = Math.sqrt(norm);
        if (norm > 0) {
            for (int i = 0; i < vec.length; i++) {
                vec[i] /= norm;
            }
        }
        return vec;
    }

    public static double cosine(double[] a, double[] b) {
        if (a == null || b == null || a.length != b.length) {
            return 0;
        }
        double dot = 0;
        for (int i = 0; i < a.length; i++) {
            dot += a[i] * b[i];
        }
        return dot; // 已归一化，点积即余弦
    }

    public static String toJson(double[] vec) {
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < vec.length; i++) {
            if (i > 0) {
                sb.append(',');
            }
            sb.append(String.format(java.util.Locale.ROOT, "%.6f", vec[i]));
        }
        return sb.append(']').toString();
    }

    /**
     * JSON 数组 → 向量（维度动态，由数组长度决定）。
     * Mock 128 维与真实平台（如豆包 2048 维）向量共存：余弦要求等长，跨维度比较得 0 分，
     * 切换 embedding 模型后须调 /agent/admin/rag/reembed-all 重灌存量向量。
     */
    public static double[] fromJson(String json) {
        if (json == null || json.length() < 2) {
            return new double[0];
        }
        String body = json.substring(1, json.length() - 1);
        if (body.isBlank()) {
            return new double[0];
        }
        String[] parts = body.split(",");
        double[] vec = new double[parts.length];
        for (int i = 0; i < parts.length; i++) {
            try {
                vec[i] = Double.parseDouble(parts[i].trim());
            } catch (NumberFormatException ignored) {
                // 解析失败的分量按 0 处理
            }
        }
        return vec;
    }
}
