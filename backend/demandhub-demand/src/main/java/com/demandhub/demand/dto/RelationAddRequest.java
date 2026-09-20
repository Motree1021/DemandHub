package com.demandhub.demand.dto;

/**
 * 需求关联请求（relationType: PARENT/DEPENDS/DUPLICATE/SPLIT）
 */
public record RelationAddRequest(Long demandId, Long relatedDemandId, String relationType) {
}
