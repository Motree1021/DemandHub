package com.demandhub.system.controller;

import com.demandhub.common.core.Result;
import com.demandhub.system.entity.OrgSnapshot;
import com.demandhub.system.mapper.OrgSnapshotMapper;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.Data;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 组织镜像只读查询（主数据来自权限中心，本地无增删改）
 */
@Tag(name = "组织镜像")
@RestController
@RequestMapping("/system/org")
public class OrgController {

    private final OrgSnapshotMapper orgMapper;

    public OrgController(OrgSnapshotMapper orgMapper) {
        this.orgMapper = orgMapper;
    }

    @Operation(summary = "组织树")
    @GetMapping("/tree")
    public Result<List<OrgNodeVO>> tree() {
        List<OrgSnapshot> all = orgMapper.selectList(null);
        Map<Long, OrgNodeVO> nodeMap = new LinkedHashMap<>();
        all.stream().sorted(Comparator.comparing(OrgSnapshot::getOrgId)).forEach(o -> {
            OrgNodeVO node = new OrgNodeVO();
            node.setOrgId(o.getOrgId());
            node.setName(o.getName());
            node.setLevel(o.getLevel());
            node.setParentId(o.getParentId());
            node.setOrgKind(o.getOrgKind());
            nodeMap.put(o.getOrgId(), node);
        });
        List<OrgNodeVO> roots = new ArrayList<>();
        nodeMap.forEach((id, node) -> {
            OrgNodeVO parent = nodeMap.get(node.getParentId());
            if (parent == null) {
                roots.add(node);
            } else {
                parent.getChildren().add(node);
            }
        });
        return Result.ok(roots);
    }

    @Operation(summary = "组织平铺列表")
    @GetMapping("/list")
    public Result<List<OrgSnapshot>> list() {
        return Result.ok(orgMapper.selectList(null));
    }

    @Data
    public static class OrgNodeVO implements Serializable {
        private Long orgId;
        private String name;
        private String level;
        private Long parentId;
        private String orgKind;
        private List<OrgNodeVO> children = new ArrayList<>();
    }
}
