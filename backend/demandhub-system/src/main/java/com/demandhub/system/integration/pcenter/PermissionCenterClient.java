package com.demandhub.system.integration.pcenter;

import com.demandhub.system.integration.pcenter.dto.MasterDataChanges;
import com.demandhub.system.integration.pcenter.dto.PcOrg;
import com.demandhub.system.integration.pcenter.dto.PcUser;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 零售业务线统一权限中心客户端（IR-06/07/08/09）。
 * 一期外部依赖 Mock：由 {@link MockPermissionCenterClient} 提供内存数据源；
 * 二期切换真实 HTTP 实现时保持本接口不变。
 */
public interface PermissionCenterClient {

    /** 按企微 userid 查用户详情（OAuth 登录后调用） */
    PcUser getUserByWecomId(String wecomId);

    PcUser getUserByUserId(String userId);

    /** 全量：所有用户 */
    List<PcUser> listAllUsers();

    /** 全量：所有组织节点 */
    List<PcOrg> listAllOrgs();

    /** 增量：拉取 watermark 之后的变更 */
    MasterDataChanges listChanges(LocalDateTime watermark);

    /** 一期 Mock 辅助：模拟权限中心中某用户调岗（触发增量变更） */
    void simulateUserMove(String userId, Long newOrgId);
}
