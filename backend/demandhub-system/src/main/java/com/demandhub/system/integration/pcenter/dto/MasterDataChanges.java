package com.demandhub.system.integration.pcenter.dto;

import lombok.Data;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

/**
 * 权限中心增量变更（IR-08，带增量水印）
 */
@Data
public class MasterDataChanges implements Serializable {

    private List<PcUser> users = new ArrayList<>();

    private List<PcOrg> orgs = new ArrayList<>();

    public boolean isEmpty() {
        return users.isEmpty() && orgs.isEmpty();
    }
}
