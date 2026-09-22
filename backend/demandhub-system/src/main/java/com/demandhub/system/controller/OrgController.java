package com.demandhub.system.controller;

import com.demandhub.common.annotation.RequireRole;
import com.demandhub.common.core.Result;
import com.demandhub.system.dto.OrgSaveRequest;
import com.demandhub.system.entity.OrgSnapshot;
import com.demandhub.system.mapper.OrgSnapshotMapper;
import com.demandhub.system.service.OrgService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.Data;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 组织管理（FR-M1-02）：树/平铺查询 + CRUD（含子树路径重算与删除引用校验）。
 * 查询端点对登录用户开放（提报选人/选组织用）；写操作仅系统管理员。
 */
@Tag(name = "组织管理")
@RestController
@RequestMapping("/system/org")
public class OrgController {

    private final OrgSnapshotMapper orgMapper;
    private final OrgService orgService;

    public OrgController(OrgSnapshotMapper orgMapper, OrgService orgService) {
        this.orgMapper = orgMapper;
        this.orgService = orgService;
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
            node.setPath(o.getPath());
            node.setOrgKind(o.getOrgKind());
            node.setExternalFlag(o.getExternalFlag());
            node.setExternalDeptId(o.getExternalDeptId());
            node.setStatus(o.getStatus());
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

    @Operation(summary = "新增组织（路径按父节点自动生成）")
    @RequireRole("ADMIN")
    @PostMapping
    public Result<Long> create(@Valid @RequestBody OrgSaveRequest request) {
        return Result.ok(orgService.create(request));
    }

    @Operation(summary = "修改组织（parentId 变更触发子树路径重算；external_dept_id 维护）")
    @RequireRole("ADMIN")
    @PutMapping("/{id}")
    public Result<Void> update(@PathVariable Long id, @Valid @RequestBody OrgSaveRequest request) {
        request.setId(id);
        orgService.update(request);
        return Result.ok();
    }

    @Operation(summary = "删除组织（子组织/用户/授权/需求引用校验；根与外部虚拟组织禁删）")
    @RequireRole("ADMIN")
    @DeleteMapping("/{id}")
    public Result<Void> delete(@PathVariable Long id) {
        orgService.delete(id);
        return Result.ok();
    }

    @Data
    public static class OrgNodeVO implements Serializable {
        private Long orgId;
        private String name;
        private String level;
        private Long parentId;
        private String path;
        private String orgKind;
        private Integer externalFlag;
        private String externalDeptId;
        private String status;
        private List<OrgNodeVO> children = new ArrayList<>();
    }
}
