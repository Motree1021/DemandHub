package com.demandhub.agent.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.agent.entity.DemandView;
import com.demandhub.agent.entity.KnowledgeDocEntity;
import com.demandhub.agent.entity.ReviewView;
import com.demandhub.agent.entity.SolutionRowEntity;
import com.demandhub.agent.llm.LlmClient;
import com.demandhub.agent.llm.LlmUnavailableException;
import com.demandhub.agent.llm.MockEmbedding;
import com.demandhub.agent.mapper.AgentDemandViewMapper;
import com.demandhub.agent.mapper.KnowledgeDocMapper;
import com.demandhub.agent.mapper.ReviewViewMapper;
import com.demandhub.agent.mapper.SolutionRowMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;

/**
 * RAG 知识库（FR-M9-03 / 架构 4.7）：
 * 验收通过（DONE）的需求方案+评审意见异步向量化入库；处理新需求时按语义相似度推荐 Top N。
 * 一期：MySQL JSON 列存向量 + 应用层余弦相似度；二期可平移 pgvector（表结构与接口不变）。
 */
@Slf4j
@Service
public class RagService {

    /** 相似度阈值（余弦，归一化向量）：低于不推荐 */
    private static final double SCORE_THRESHOLD = 0.08;

    private final KnowledgeDocMapper knowledgeDocMapper;
    private final AgentDemandViewMapper demandViewMapper;
    private final SolutionRowMapper solutionRowMapper;
    private final ReviewViewMapper reviewViewMapper;
    private final LlmClient llmClient;

    public RagService(KnowledgeDocMapper knowledgeDocMapper, AgentDemandViewMapper demandViewMapper,
                      SolutionRowMapper solutionRowMapper, ReviewViewMapper reviewViewMapper,
                      LlmClient llmClient) {
        this.knowledgeDocMapper = knowledgeDocMapper;
        this.demandViewMapper = demandViewMapper;
        this.solutionRowMapper = solutionRowMapper;
        this.reviewViewMapper = reviewViewMapper;
        this.llmClient = llmClient;
    }

    /** 相似需求卡片 */
    public record SimilarDoc(Long demandId, String demandNo, String title, String demandTypeCode, double score) {
    }

    /**
     * 相似历史需求 Top N（处理人打开新需求时调用）。
     * 注：返回 DONE 需求的编号/标题等低敏元数据，登录即可查；需求本体详情仍受 demand 服务数据权限控制。
     */
    public List<SimilarDoc> similar(Long demandId, int topN) {
        DemandView demand = demandViewMapper.selectById(demandId);
        if (demand == null) {
            return List.of();
        }
        final double[] queryVec;
        try {
            queryVec = llmClient.embed(demand.getTitle() + "\n" + (demand.getContent() == null ? "" : demand.getContent()));
        } catch (LlmUnavailableException e) {
            // embedding 平台不可用：相似推荐降级为空，不影响处理主流程
            log.warn("[RAG] embedding 不可用，相似推荐跳过, demandId={}", demandId);
            return List.of();
        }
        List<KnowledgeDocEntity> docs = knowledgeDocMapper.selectList(new LambdaQueryWrapper<KnowledgeDocEntity>()
                .eq(KnowledgeDocEntity::getStatus, "ACTIVE")
                .ne(KnowledgeDocEntity::getDemandId, demandId));
        if (docs.isEmpty()) {
            return List.of();
        }
        List<SimilarDoc> scored = new ArrayList<>();
        for (KnowledgeDocEntity doc : docs) {
            double score = MockEmbedding.cosine(queryVec, MockEmbedding.fromJson(doc.getEmbedding()));
            if (score >= SCORE_THRESHOLD) {
                scored.add(new SimilarDoc(doc.getDemandId(), doc.getDemandNo(), doc.getTitle(),
                        doc.getDemandTypeCode(), Math.round(score * 1000.0) / 1000.0));
            }
        }
        return scored.stream()
                .sorted(Comparator.comparingDouble(SimilarDoc::score).reversed())
                .limit(Math.max(1, topN))
                .toList();
    }

    /** 检索 Top N 完整文档（处理辅助生成时引用） */
    public List<KnowledgeDocEntity> similarDocs(Long demandId, int topN) {
        List<SimilarDoc> hits = similar(demandId, topN);
        if (hits.isEmpty()) {
            return List.of();
        }
        List<Long> ids = hits.stream().map(SimilarDoc::demandId).toList();
        List<KnowledgeDocEntity> docs = knowledgeDocMapper.selectList(new LambdaQueryWrapper<KnowledgeDocEntity>()
                .in(KnowledgeDocEntity::getDemandId, ids));
        // 按命中顺序返回
        return ids.stream()
                .flatMap(id -> docs.stream().filter(d -> d.getDemandId().equals(id)).limit(1))
                .toList();
    }

    /**
     * 验收通过后向量化入库（由 MQ 消费者调用；uk_demand 幂等）。
     * 内容 = 标题 + 需求描述 + 最新方案 + 评审意见。
     */
    public void vectorizeDoneDemand(Long demandId) {
        Long exists = knowledgeDocMapper.selectCount(new LambdaQueryWrapper<KnowledgeDocEntity>()
                .eq(KnowledgeDocEntity::getDemandId, demandId));
        if (exists != null && exists > 0) {
            return;
        }
        DemandView demand = demandViewMapper.selectById(demandId);
        if (demand == null || !"DONE".equals(demand.getStatus())) {
            log.warn("[RAG] 跳过向量化：需求不存在或非 DONE, demandId={}", demandId);
            return;
        }
        StringBuilder content = new StringBuilder();
        content.append(demand.getTitle()).append('\n');
        if (demand.getContent() != null) {
            content.append(demand.getContent()).append('\n');
        }
        SolutionRowEntity solution = solutionRowMapper.selectOne(new LambdaQueryWrapper<SolutionRowEntity>()
                .eq(SolutionRowEntity::getDemandId, demandId)
                .orderByDesc(SolutionRowEntity::getVersion)
                .last("LIMIT 1"));
        if (solution != null) {
            if (solution.getSpecContent() != null) {
                content.append("【需求规约】").append(solution.getSpecContent()).append('\n');
            }
            if (solution.getSolutionContent() != null) {
                content.append("【方案】").append(solution.getSolutionContent()).append('\n');
            }
        }
        List<ReviewView> reviews = reviewViewMapper.selectList(new LambdaQueryWrapper<ReviewView>()
                .eq(ReviewView::getDemandId, demandId)
                .orderByAsc(ReviewView::getId));
        for (ReviewView r : reviews) {
            if (r.getComment() != null && !r.getComment().isBlank()) {
                content.append("【评审意见-").append(r.getConclusion()).append("】").append(r.getComment()).append('\n');
            }
        }

        KnowledgeDocEntity doc = new KnowledgeDocEntity();
        doc.setDemandId(demand.getId());
        doc.setDemandNo(demand.getDemandNo());
        doc.setTitle(demand.getTitle());
        doc.setDemandTypeCode(demand.getDemandTypeCode());
        doc.setContent(content.toString());
        try {
            doc.setEmbedding(MockEmbedding.toJson(llmClient.embed(content.toString())));
        } catch (LlmUnavailableException e) {
            // embedding 平台不可用：本次向量化跳过（可由 /rag/reembed-all 或 /rag/vectorize 补偿）
            log.warn("[RAG] embedding 不可用，向量化跳过, demandId={}", demandId);
            return;
        }
        doc.setStatus("ACTIVE");
        knowledgeDocMapper.insert(doc);
        log.info("[RAG] 需求 {} 已向量化入库（{} 字）", demand.getDemandNo(), content.length());
    }

    /** 重建全部知识向量（切换 embedding 模型/维度后执行；逐篇容错，失败计数不中断） */
    public Map<String, Object> reembedAll() {
        List<KnowledgeDocEntity> docs = knowledgeDocMapper.selectList(null);
        int success = 0;
        int failed = 0;
        for (KnowledgeDocEntity doc : docs) {
            try {
                doc.setEmbedding(MockEmbedding.toJson(llmClient.embed(doc.getContent())));
                knowledgeDocMapper.updateById(doc);
                success++;
            } catch (Exception e) {
                failed++;
                log.warn("[RAG] 重建向量失败, docId={}, reason={}", doc.getId(), e.getMessage());
            }
        }
        log.info("[RAG] 向量重建完成：total={}, success={}, failed={}", docs.size(), success, failed);
        return Map.of("total", docs.size(), "success", success, "failed", failed);
    }

    /** 知识库规模（健康检查/自测用） */
    public long docCount() {
        Long cnt = knowledgeDocMapper.selectCount(new LambdaQueryWrapper<KnowledgeDocEntity>()
                .eq(KnowledgeDocEntity::getStatus, "ACTIVE"));
        return cnt == null ? 0 : cnt;
    }
}
