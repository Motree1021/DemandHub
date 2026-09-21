<template>
  <div class="detail-page" v-loading="loading">
    <template v-if="detail">
      <!-- 头部：标题 + 状态 + 操作栏 -->
      <el-card shadow="never" class="head-card">
        <div class="head-row">
          <div>
            <div class="title-row">
              <span class="demand-title">{{ detail.demand.title }}</span>
              <el-tag :type="statusTagType(detail.demand.status)">{{ statusLabel(detail.demand.status) }}</el-tag>
              <el-tag v-if="detail.demand.onHold === 1" type="danger">已挂起{{ detail.holdDays != null ? ` ${detail.holdDays} 天` : '' }}</el-tag>
              <el-tag :type="urgencyTagType(detail.demand.urgency)">{{ urgencyLabel(detail.demand.urgency) }}</el-tag>
            </div>
            <div class="muted head-sub">
              {{ detail.demand.demandNo }}　提交于 {{ fmtTime(detail.demand.submittedAt) }}　提报人：{{ detail.submitterName || '-' }}<template v-if="detail.actualDemanderName">（代 {{ detail.actualDemanderName }} 提报）</template>
            </div>
          </div>
          <div class="action-bar">
            <el-button v-if="hasAction('WITHDRAW')" type="danger" plain @click="dlg.withdraw = true">撤销</el-button>
            <el-button v-if="hasAction('RESUBMIT')" type="primary" @click="openResubmit">重新提交</el-button>
            <el-button v-if="hasAction('ACCEPT')" type="primary" @click="dlg.accept = true">受理</el-button>
            <el-button v-if="hasAction('RETURN')" type="warning" plain @click="dlg.returnBack = true">退回补充</el-button>
            <el-button v-if="hasAction('CLOSE')" type="danger" plain @click="dlg.close = true">关闭</el-button>
            <el-button v-if="hasAction('ASSIGN')" type="primary" @click="openAssign">分派</el-button>
            <el-button v-if="hasAction('CLAIM')" type="primary" @click="onClaim">领取</el-button>
            <el-button v-if="hasAction('CHANGE_TYPE')" plain @click="dlg.changeType = true">类型修正</el-button>
            <el-button v-if="hasAction('SUBMIT_SOLUTION')" type="primary" @click="openSolutionEdit()">提交方案</el-button>
            <el-button v-if="hasAction('REVIEW')" type="primary" @click="dlg.review = true">方案评审</el-button>
            <el-button v-if="hasAction('START')" type="primary" @click="onStart">开始处理</el-button>
            <el-button v-if="hasAction('HOLD')" type="warning" plain @click="dlg.hold = true">挂起</el-button>
            <el-button v-if="hasAction('RESUME')" type="primary" plain @click="onResume">恢复</el-button>
            <el-button v-if="hasAction('SUBMIT_ACCEPTANCE')" type="primary" @click="onSubmitAcceptance">提交验收</el-button>
            <el-button v-if="hasAction('ACCEPTANCE_REVIEW')" type="primary" @click="dlg.acceptance = true">验收结论</el-button>
            <el-dropdown v-if="hasAction('SPLIT') || hasAction('RELATE')" trigger="click">
              <el-button plain>更多<el-icon><ArrowDown /></el-icon></el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-if="hasAction('RELATE')" @click="dlg.relate = true">关联需求</el-dropdown-item>
                  <el-dropdown-item v-if="hasAction('SPLIT')" @click="openSplit">拆分需求</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </el-card>

      <el-row :gutter="16">
        <!-- 左列 -->
        <el-col :span="17">
          <!-- 需求内容 -->
          <el-card shadow="never" class="mb16">
            <template #header>需求内容</template>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="需求类型">{{ typeLabel(detail.demand.demandTypeCode, detail.typeName) }}</el-descriptions-item>
              <el-descriptions-item label="期望交付">{{ fmtDate(detail.demand.expectDeliveryAt) }}</el-descriptions-item>
              <template v-if="detail.demand.demandTypeCode === 'TECH' && detail.ext">
                <el-descriptions-item label="关联系统">{{ detail.ext.relatedSystem || '-' }}</el-descriptions-item>
                <el-descriptions-item label="关联模块">{{ detail.ext.relatedModule || '-' }}</el-descriptions-item>
                <el-descriptions-item label="业务场景" :span="2">{{ detail.ext.businessScenario || '-' }}</el-descriptions-item>
                <el-descriptions-item label="验收标准" :span="2">{{ detail.ext.acceptanceCriteria || '-' }}</el-descriptions-item>
              </template>
              <template v-if="detail.demand.demandTypeCode === 'MATL' && detail.ext">
                <el-descriptions-item label="物料子类">{{ detail.ext.materialSubtype || '-' }}</el-descriptions-item>
                <el-descriptions-item label="数量">{{ detail.ext.quantity ?? '-' }}</el-descriptions-item>
                <el-descriptions-item label="使用场景">{{ detail.ext.usageScenario || '-' }}</el-descriptions-item>
                <el-descriptions-item label="期望到位">{{ fmtDate(detail.ext.expectedArrivalAt) }}</el-descriptions-item>
              </template>
              <template v-if="detail.demand.demandTypeCode === 'TRAIN' && detail.ext">
                <el-descriptions-item label="培训子类">{{ detail.ext.trainingSubtype || '-' }}</el-descriptions-item>
                <el-descriptions-item label="培训人数">{{ detail.ext.traineeCount ?? '-' }}</el-descriptions-item>
                <el-descriptions-item label="培训对象">{{ detail.ext.traineeObject || '-' }}</el-descriptions-item>
                <el-descriptions-item label="期望完成">{{ fmtDate(detail.ext.expectedCompleteAt) }}</el-descriptions-item>
              </template>
              <el-descriptions-item label="需求描述" :span="2">
                <div class="pre-wrap">{{ detail.demand.content }}</div>
              </el-descriptions-item>
              <el-descriptions-item label="附件" :span="2">
                <template v-if="detail.attachments.length">
                  <div v-for="att in detail.attachments" :key="att.id" class="att-item">
                    <el-icon><Paperclip /></el-icon>
                    <span class="att-name">{{ att.fileName }}</span>
                    <span class="muted">{{ fmtSize(att.fileSize) }}</span>
                    <el-button v-if="isImage(att)" link type="primary" @click="onPreview(att)">预览</el-button>
                    <el-button link type="primary" @click="onDownload(att)">下载</el-button>
                  </div>
                </template>
                <span v-else class="muted">无附件</span>
              </el-descriptions-item>
            </el-descriptions>
          </el-card>

          <!-- 流转时间线 -->
          <el-card shadow="never" class="mb16">
            <template #header>处理进展时间线</template>
            <el-empty v-if="!transitions.length" description="暂无流转记录" :image-size="60" />
            <el-timeline v-else>
              <el-timeline-item
                v-for="t in transitions"
                :key="t.id"
                :timestamp="fmtTime(t.createdAt, true)"
                placement="top"
                :type="t.id === transitions[transitions.length - 1].id ? 'primary' : 'success'"
                :hollow="t.id !== transitions[transitions.length - 1].id"
              >
                <div class="tl-title">
                  <b>{{ eventLabel(t.action) }}</b>
                  <span class="muted" style="margin-left: 8px">
                    {{ t.fromStatus ? statusLabel(t.fromStatus) : '开始' }} → {{ statusLabel(t.toStatus) }}
                  </span>
                </div>
                <div class="muted">操作人：{{ t.operatorSnapshot || userName(t.operatorId) }}</div>
                <div v-if="t.comment" class="tl-comment">意见：{{ t.comment }}</div>
              </el-timeline-item>
            </el-timeline>
          </el-card>

          <!-- 方案区 -->
          <el-card v-if="solutions.length || hasAction('SUBMIT_SOLUTION')" shadow="never" class="mb16">
            <template #header>
              <div class="card-header">
                <span>处理方案（{{ solutions.length }} 个版本）</span>
                <el-button v-if="hasAction('SUBMIT_SOLUTION')" size="small" type="primary" @click="openSolutionEdit()">新建方案版本</el-button>
              </div>
            </template>
            <el-empty v-if="!solutions.length" description="暂无方案" :image-size="60" />
            <el-tabs v-else v-model="activeSolutionTab">
              <el-tab-pane v-for="s in solutions" :key="s.id" :name="String(s.id)">
                <template #label>
                  V{{ s.version }}
                  <el-tag size="small" :type="solutionTagType(s.status)" style="margin-left: 4px">{{ solutionStatusLabel(s.status) }}</el-tag>
                  <el-icon v-if="s.status === 'APPROVED'" color="#16a34a" style="margin-left: 2px"><CircleCheckFilled /></el-icon>
                </template>
                <el-descriptions :column="2" size="small" border>
                  <el-descriptions-item label="作者">{{ userName(s.authorId) }}</el-descriptions-item>
                  <el-descriptions-item label="计划交付">{{ fmtDate(s.planDeliveryAt) }}</el-descriptions-item>
                  <el-descriptions-item label="需求理解 / 规格" :span="2"><div class="pre-wrap">{{ s.specContent || '-' }}</div></el-descriptions-item>
                  <el-descriptions-item label="方案内容" :span="2"><div class="pre-wrap">{{ s.solutionContent || '-' }}</div></el-descriptions-item>
                  <el-descriptions-item v-if="s.remark" label="备注" :span="2">{{ s.remark }}</el-descriptions-item>
                </el-descriptions>
                <div v-if="s.status === 'DRAFT' && s.authorId === userStore.userInfo?.id" style="margin-top: 10px">
                  <el-button size="small" @click="openSolutionEdit(s)">编辑</el-button>
                  <el-button size="small" type="primary" @click="onSubmitSolutionReview(s)">提交评审</el-button>
                </div>
                <div v-if="s.status === 'REVIEWING' && hasAction('REVIEW')" style="margin-top: 10px">
                  <el-button size="small" type="primary" @click="dlg.review = true">评审该版本</el-button>
                </div>
                <!-- 该版本评审记录 -->
                <div v-if="reviewsOf(s.id).length" class="review-list">
                  <div v-for="r in reviewsOf(s.id)" :key="r.id" class="review-item">
                    <el-tag size="small" :type="r.conclusion === 'PASS' ? 'success' : 'danger'">{{ r.conclusion === 'PASS' ? '通过' : '打回' }}</el-tag>
                    <b style="margin: 0 6px">{{ userName(r.reviewerId) }}</b>
                    <span class="muted">{{ fmtTime(r.reviewedAt) }}</span>
                    <div v-if="r.comment" class="muted">意见：{{ r.comment }}</div>
                  </div>
                </div>
              </el-tab-pane>
            </el-tabs>
          </el-card>

          <!-- 工时记录 -->
          <el-card v-if="efforts.length || hasAction('EFFORT')" shadow="never" class="mb16">
            <template #header>
              <div class="card-header">
                <span>工时记录<template v-if="summary">（共 {{ summary.totalHours }}h）</template></span>
                <el-button v-if="hasAction('EFFORT')" size="small" type="primary" @click="dlg.effort = true">填报工时</el-button>
              </div>
            </template>
            <el-table v-if="efforts.length" :data="efforts" size="small" border>
              <el-table-column label="日期" width="110">
                <template #default="{ row }">{{ fmtDate(row.workDate) }}</template>
              </el-table-column>
              <el-table-column label="人员" width="110">
                <template #default="{ row }">{{ userName(row.userId) }}</template>
              </el-table-column>
              <el-table-column prop="hours" label="工时(h)" width="90" />
              <el-table-column prop="description" label="工作内容" min-width="200" show-overflow-tooltip />
            </el-table>
            <el-empty v-else description="暂无工时记录" :image-size="60" />
            <div v-if="summary && summary.byUser.length" class="effort-summary">
              <span class="muted">按人汇总：</span>
              <el-tag v-for="u in summary.byUser" :key="u.userId" size="small" style="margin-right: 8px">{{ userName(u.userId) }} {{ u.hours }}h</el-tag>
            </div>
          </el-card>

          <!-- 评论区 -->
          <el-card shadow="never" class="mb16">
            <template #header>评论与沟通（{{ comments.length }}）</template>
            <div v-for="c in comments" :key="c.id" class="comment-item">
              <div>
                <b>{{ userName(c.authorId) }}</b>
                <span class="muted" style="margin-left: 8px">{{ fmtTime(c.createdAt, true) }}</span>
              </div>
              <div class="comment-content">{{ c.content }}</div>
            </div>
            <el-empty v-if="!comments.length" description="暂无评论" :image-size="60" />
            <template v-if="hasAction('COMMENT')">
              <el-input v-model="commentInput" type="textarea" :rows="3" placeholder="发表评论，可 @同事 提醒" style="margin-top: 12px" />
              <div class="comment-bar">
                <el-select v-model="mentionIds" multiple filterable placeholder="@提醒谁看（可多选）" style="width: 320px">
                  <el-option v-for="u in allUsers" :key="u.id" :label="u.name" :value="u.id" />
                </el-select>
                <el-button type="primary" :disabled="!commentInput.trim()" :loading="commenting" @click="onAddComment">发送</el-button>
              </div>
            </template>
          </el-card>
        </el-col>

        <!-- 右列 -->
        <el-col :span="7">
          <el-card shadow="never" class="mb16">
            <template #header>处理信息</template>
            <dl class="kv">
              <dt>承接组织</dt>
              <dd>{{ detail.assigneeOrgName || '-' }}</dd>
              <dt>当前处理人</dt>
              <dd>{{ detail.assigneeUserName || '未分派' }}</dd>
              <dt>提报部门</dt>
              <dd>{{ detail.demand.submitterOrgSnapshot || '-' }}</dd>
              <dt>来源渠道</dt>
              <dd>{{ channelLabel(detail.demand.channel) }}</dd>
              <dt>挂起状态</dt>
              <dd>
                <template v-if="detail.demand.onHold === 1">
                  <span style="color: var(--el-color-danger)">已挂起（{{ detail.demand.holdReason || '-' }}）</span>
                </template>
                <template v-else>未挂起</template>
              </dd>
              <template v-if="detail.demand.status === 'DONE'">
                <dt>质量评分</dt>
                <dd>{{ detail.demand.qualityScore ? `${detail.demand.qualityScore} 分` : '-' }}</dd>
                <dt>满意度</dt>
                <dd>{{ detail.demand.satisfactionScore ? `${detail.demand.satisfactionScore} 分` : '-' }}</dd>
                <dt>实际交付</dt>
                <dd>{{ fmtTime(detail.demand.actualDeliveryAt) }}</dd>
              </template>
              <template v-if="detail.demand.status === 'CLOSED'">
                <dt>关闭原因</dt>
                <dd>{{ detail.demand.closeReason || '-' }}</dd>
                <dt>关闭时间</dt>
                <dd>{{ fmtTime(detail.demand.closedAt) }}</dd>
              </template>
            </dl>
          </el-card>

          <!-- 关联需求 -->
          <el-card shadow="never" class="mb16">
            <template #header>
              <div class="card-header">
                <span>相关需求</span>
                <el-button v-if="hasAction('RELATE')" size="small" text type="primary" @click="dlg.relate = true">+ 关联</el-button>
              </div>
            </template>
            <el-empty v-if="!relations.length" description="暂无关联" :image-size="50" />
            <div v-for="r in relations" :key="r.id" class="relation-item">
              <el-tag size="small" effect="plain">{{ relationLabel(r) }}</el-tag>
              <el-link type="primary" style="margin-left: 8px" @click="goRelated(r)">{{ relationDemandNo(r) }}</el-link>
              <span class="muted" style="margin-left: 6px">{{ relationTitle(r) }}</span>
            </div>
          </el-card>

          <!-- RAG 相似历史需求（处理人/经理/管理者可见） -->
          <SimilarDemandsCard v-if="canViewSimilar" :demand-id="demandId" />

          <!-- AI 处理助手（处理人/经理可用；产出草稿需人工确认才入方案表） -->
          <AgentAssistPanel
            v-if="canUseAgentAssist"
            :demand-id="demandId"
            :demand-status="detail.demand.status"
            @confirmed="loadAll"
          />
        </el-col>
      </el-row>
    </template>

    <!-- ===== 操作弹窗 ===== -->
    <el-dialog v-model="dlg.withdraw" title="撤销需求" width="440px">
      <el-input v-model="opForm.reason" type="textarea" :rows="3" placeholder="请填写撤销原因（必填）" />
      <template #footer>
        <el-button @click="dlg.withdraw = false">取消</el-button>
        <el-button type="danger" :disabled="!opForm.reason?.trim()" :loading="opLoading" @click="onWithdraw">确认撤销</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="dlg.accept" title="受理需求" width="440px">
      <el-input v-model="opForm.comment" type="textarea" :rows="3" placeholder="受理意见（选填）" />
      <template #footer>
        <el-button @click="dlg.accept = false">取消</el-button>
        <el-button type="primary" :loading="opLoading" @click="onAccept">确认受理</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="dlg.returnBack" title="退回补充" width="440px">
      <el-input v-model="opForm.comment" type="textarea" :rows="3" placeholder="请说明需要补充的内容（必填）" />
      <template #footer>
        <el-button @click="dlg.returnBack = false">取消</el-button>
        <el-button type="warning" :disabled="!opForm.comment?.trim()" :loading="opLoading" @click="onReturn">确认退回</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="dlg.close" title="关闭需求" width="440px">
      <el-input v-model="opForm.reason" type="textarea" :rows="3" placeholder="请填写关闭原因（必填）" />
      <template #footer>
        <el-button @click="dlg.close = false">取消</el-button>
        <el-button type="danger" :disabled="!opForm.reason?.trim()" :loading="opLoading" @click="onClose">确认关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="dlg.assign" title="分派处理人" width="440px">
      <el-form label-width="80px">
        <el-form-item label="处理人" required>
          <UserSelect v-model="opForm.assigneeId" placeholder="选择处理人" />
        </el-form-item>
        <el-form-item label="分派意见">
          <el-input v-model="opForm.comment" type="textarea" :rows="3" placeholder="选填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg.assign = false">取消</el-button>
        <el-button type="primary" :disabled="!opForm.assigneeId" :loading="opLoading" @click="onAssign">确认分派</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="dlg.changeType" title="类型修正" width="440px">
      <el-form label-width="80px">
        <el-form-item label="新类型" required>
          <el-select v-model="opForm.newTypeCode" style="width: 100%">
            <el-option v-for="t in typeList" :key="t.typeCode" :label="t.typeName" :value="t.typeCode" />
          </el-select>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="opForm.comment" type="textarea" :rows="2" placeholder="选填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg.changeType = false">取消</el-button>
        <el-button type="primary" :disabled="!opForm.newTypeCode" :loading="opLoading" @click="onChangeType">确认修正</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="dlg.hold" title="挂起需求" width="440px">
      <el-input v-model="opForm.reason" type="textarea" :rows="3" placeholder="请填写挂起原因（必填）" />
      <template #footer>
        <el-button @click="dlg.hold = false">取消</el-button>
        <el-button type="warning" :disabled="!opForm.reason?.trim()" :loading="opLoading" @click="onHold">确认挂起</el-button>
      </template>
    </el-dialog>

    <!-- 重新提交（NEED_INFO） -->
    <el-dialog v-model="dlg.resubmit" title="补充后重新提交" width="640px">
      <el-form label-width="100px">
        <el-form-item label="需求标题" required>
          <el-input v-model="opForm.title" maxlength="100" />
        </el-form-item>
        <el-form-item label="需求描述" required>
          <el-input v-model="opForm.content" type="textarea" :rows="5" maxlength="2000" />
        </el-form-item>
        <el-form-item label="紧急程度">
          <el-select v-model="opForm.urgency" style="width: 200px">
            <el-option label="普通" value="NORMAL" />
            <el-option label="紧急" value="URGENT" />
            <el-option label="特急" value="CRITICAL" />
          </el-select>
        </el-form-item>
        <el-form-item label="期望交付">
          <el-date-picker v-model="opForm.expectDeliveryAt" type="date" value-format="YYYY-MM-DDT00:00:00" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg.resubmit = false">取消</el-button>
        <el-button type="primary" :disabled="!opForm.title?.trim() || !opForm.content?.trim()" :loading="opLoading" @click="onResubmit">重新提交</el-button>
      </template>
    </el-dialog>

    <!-- 方案编辑 -->
    <el-dialog v-model="dlg.solution" :title="opForm.solutionId ? `编辑方案 V${opForm.solutionVersion}` : '新建方案版本'" width="720px">
      <el-form label-width="110px">
        <el-form-item label="需求理解/规格">
          <el-input v-model="opForm.specContent" type="textarea" :rows="4" placeholder="对需求的理解与规格确认" />
        </el-form-item>
        <el-form-item label="方案内容">
          <el-input v-model="opForm.solutionContent" type="textarea" :rows="6" placeholder="实现方案、排期、资源投入等" />
        </el-form-item>
        <el-form-item label="计划交付时间">
          <el-date-picker v-model="opForm.planDeliveryAt" type="date" value-format="YYYY-MM-DDT00:00:00" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="opForm.remark" maxlength="200" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg.solution = false">取消</el-button>
        <el-button :loading="opLoading" @click="onSaveSolution(false)">保存草稿</el-button>
        <el-button type="primary" :loading="opLoading" @click="onSaveSolution(true)">保存并提交评审</el-button>
      </template>
    </el-dialog>

    <!-- 方案评审 -->
    <el-dialog v-model="dlg.review" title="方案评审" width="440px">
      <el-form label-width="80px">
        <el-form-item label="结论" required>
          <el-radio-group v-model="opForm.conclusion">
            <el-radio value="PASS">通过</el-radio>
            <el-radio value="REJECT">打回</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="评审意见">
          <el-input v-model="opForm.comment" type="textarea" :rows="3" :placeholder="opForm.conclusion === 'REJECT' ? '打回必填意见' : '选填'" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg.review = false">取消</el-button>
        <el-button type="primary" :disabled="opForm.conclusion === 'REJECT' && !opForm.comment?.trim()" :loading="opLoading" @click="onReview">提交评审</el-button>
      </template>
    </el-dialog>

    <!-- 验收结论 -->
    <el-dialog v-model="dlg.acceptance" title="验收结论" width="480px">
      <el-form label-width="90px">
        <el-form-item label="结论" required>
          <el-radio-group v-model="opForm.conclusion">
            <el-radio value="PASS">验收通过</el-radio>
            <el-radio value="REJECT">打回整改</el-radio>
          </el-radio-group>
        </el-form-item>
        <template v-if="opForm.conclusion === 'PASS'">
          <el-form-item label="质量评分" required>
            <el-rate v-model="opForm.qualityScore" :max="5" />
          </el-form-item>
          <el-form-item label="满意度" required>
            <el-rate v-model="opForm.satisfactionScore" :max="5" />
          </el-form-item>
        </template>
        <el-form-item label="验收意见">
          <el-input v-model="opForm.comment" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg.acceptance = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="opForm.conclusion === 'PASS' && (!opForm.qualityScore || !opForm.satisfactionScore)"
          :loading="opLoading"
          @click="onAcceptanceReview"
        >提交结论</el-button>
      </template>
    </el-dialog>

    <!-- 工时填报 -->
    <el-dialog v-model="dlg.effort" title="填报工时" width="440px">
      <el-form label-width="90px">
        <el-form-item label="工作日期" required>
          <el-date-picker v-model="opForm.workDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="工时(h)" required>
          <el-input-number v-model="opForm.hours" :min="0.5" :max="24" :step="0.5" style="width: 100%" />
        </el-form-item>
        <el-form-item label="工作内容">
          <el-input v-model="opForm.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg.effort = false">取消</el-button>
        <el-button type="primary" :disabled="!opForm.workDate || !opForm.hours" :loading="opLoading" @click="onAddEffort">提交</el-button>
      </template>
    </el-dialog>

    <!-- 关联需求 -->
    <el-dialog v-model="dlg.relate" title="关联需求" width="480px">
      <el-form label-width="90px">
        <el-form-item label="关联类型" required>
          <el-select v-model="opForm.relationType" style="width: 100%">
            <el-option label="父子（对方是父需求）" value="PARENT" />
            <el-option label="依赖（依赖对方完成）" value="DEPENDS" />
            <el-option label="重复（与对方重复）" value="DUPLICATE" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标需求" required>
          <el-input v-model="opForm.relatedKeyword" placeholder="输入需求编号或标题关键字搜索" @input="onSearchRelated" />
          <el-select v-model="opForm.relatedDemandId" style="width: 100%; margin-top: 8px" placeholder="从搜索结果选择">
            <el-option v-for="d in relatedOptions" :key="d.id" :label="`${d.demandNo} ${d.title}`" :value="d.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg.relate = false">取消</el-button>
        <el-button type="primary" :disabled="!opForm.relatedDemandId || !opForm.relationType" :loading="opLoading" @click="onAddRelation">确认关联</el-button>
      </template>
    </el-dialog>

    <!-- 拆分需求 -->
    <el-dialog v-model="dlg.split" title="拆分子需求" width="640px">
      <el-alert type="info" :closable="false" title="拆分后将生成一条子需求（同类型），与本需求建立 SPLIT 关联" style="margin-bottom: 12px" />
      <el-form label-width="90px">
        <el-form-item label="子需求标题" required>
          <el-input v-model="opForm.title" maxlength="100" />
        </el-form-item>
        <el-form-item label="子需求描述" required>
          <el-input v-model="opForm.content" type="textarea" :rows="4" maxlength="2000" />
        </el-form-item>
        <el-form-item label="紧急程度">
          <el-select v-model="opForm.urgency" style="width: 200px">
            <el-option label="普通" value="NORMAL" />
            <el-option label="紧急" value="URGENT" />
            <el-option label="特急" value="CRITICAL" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg.split = false">取消</el-button>
        <el-button type="primary" :disabled="!opForm.title?.trim() || !opForm.content?.trim()" :loading="opLoading" @click="onSplit">确认拆分</el-button>
      </template>
    </el-dialog>

    <!-- 图片预览 -->
    <el-dialog v-model="previewVisible" :title="previewName" width="640px">
      <img :src="previewUrl" style="max-width: 100%" alt="附件预览" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import UserSelect from '@/components/UserSelect.vue'
import AgentAssistPanel from '@/components/AgentAssistPanel.vue'
import SimilarDemandsCard from '@/components/SimilarDemandsCard.vue'
import {
  getDemand,
  getTransitions,
  withdrawDemand,
  resubmitDemand,
  acceptDemand,
  returnDemand,
  closeDemand,
  assignDemand,
  claimDemand,
  changeDemandType,
  startDemand,
  holdDemand,
  resumeDemand,
  submitAcceptance,
  acceptanceReview,
  splitDemand,
  saveSolution,
  updateSolution,
  submitSolutionReview,
  reviewSolution,
  listSolutions,
  listReviews,
  addComment,
  listComments,
  addEffort,
  listEfforts,
  effortSummary,
  addRelation,
  listRelations,
  pageDemands,
  downloadAttachment,
  previewAttachmentUrl,
  type DemandDetail,
  type TransitionLog,
  type SolutionItem,
  type ReviewItem,
  type CommentItem,
  type EffortItem,
  type EffortSummary,
  type RelationItem,
  type AttachmentItem,
  type DemandListItem
} from '@/api/demand'
import { listAllUsers, listActiveTypes, type UserSnapshotVO, type DemandTypeItem } from '@/api/directory'
import { useUserStore } from '@/store/modules/user'
import { useNotificationStore } from '@/store/modules/notification'
import {
  statusLabel,
  statusTagType,
  urgencyLabel,
  urgencyTagType,
  typeLabel,
  eventLabel,
  RELATION_LABELS,
  SOLUTION_STATUS_META,
  fmtTime,
  fmtDate,
  fmtSize
} from '@/utils/format'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const notifyStore = useNotificationStore()

const demandId = Number(route.params.id)
const loading = ref(false)
const detail = ref<DemandDetail | null>(null)
const transitions = ref<TransitionLog[]>([])
const solutions = ref<SolutionItem[]>([])
const reviews = ref<ReviewItem[]>([])
const comments = ref<CommentItem[]>([])
const efforts = ref<EffortItem[]>([])
const summary = ref<EffortSummary | null>(null)
const relations = ref<RelationItem[]>([])
const relatedDemands = ref<Map<number, DemandListItem>>(new Map())
const allUsers = ref<UserSnapshotVO[]>([])
const typeList = ref<DemandTypeItem[]>([])
const activeSolutionTab = ref('')
const commentInput = ref('')
const mentionIds = ref<number[]>([])
const commenting = ref(false)
const opLoading = ref(false)
const previewVisible = ref(false)
const previewUrl = ref('')
const previewName = ref('')
const relatedOptions = ref<DemandListItem[]>([])

const dlg = reactive({
  withdraw: false,
  resubmit: false,
  accept: false,
  returnBack: false,
  close: false,
  assign: false,
  changeType: false,
  hold: false,
  solution: false,
  review: false,
  acceptance: false,
  effort: false,
  relate: false,
  split: false
})

const opForm = reactive({
  reason: '',
  comment: '',
  title: '',
  content: '',
  urgency: 'NORMAL',
  expectDeliveryAt: undefined as string | undefined,
  assigneeId: null as number | null,
  newTypeCode: '',
  conclusion: 'PASS' as 'PASS' | 'REJECT',
  qualityScore: 0,
  satisfactionScore: 0,
  solutionId: null as number | null,
  solutionVersion: 0,
  specContent: '',
  solutionContent: '',
  planDeliveryAt: undefined as string | undefined,
  remark: '',
  workDate: '',
  hours: 8,
  description: '',
  relationType: 'PARENT',
  relatedDemandId: null as number | null,
  relatedKeyword: ''
})

const userMap = computed(() => new Map(allUsers.value.map((u) => [u.id, u.name])))

/** AI 处理辅助：处理人/经理/管理员可用（与后端 /agent/assist 角色一致） */
const canUseAgentAssist = computed(
  () => userStore.roles.includes('HANDLER') || userStore.roles.includes('DEMAND_MANAGER') || userStore.isAdmin
)

/** RAG 相似推荐：处理人/经理/管理员/管理者可见（与后端 /agent/rag 角色一致） */
const canViewSimilar = computed(() => canUseAgentAssist.value || userStore.roles.includes('EXECUTIVE'))

function hasAction(action: string): boolean {
  return detail.value?.availableActions?.includes(action) ?? false
}

function userName(id: number | null | undefined): string {
  if (id == null) {
    return '-'
  }
  return userMap.value.get(id) || `#${id}`
}

function solutionStatusLabel(s: string): string {
  return SOLUTION_STATUS_META[s]?.label || s
}

function solutionTagType(s: string) {
  return SOLUTION_STATUS_META[s]?.type || 'info'
}

function channelLabel(c: string | null): string {
  const map: Record<string, string> = { WEB: 'PC 网页', WECOM_H5: '企微 H5', WECOM_BOT: '企微机器人', VOICE: '语音' }
  return (c && map[c]) || c || '-'
}

function isImage(att: AttachmentItem): boolean {
  return (att.mimeType || '').startsWith('image/')
}

function reviewsOf(solutionId: number): ReviewItem[] {
  return reviews.value.filter((r) => r.solutionId === solutionId)
}

function relationLabel(r: RelationItem): string {
  return RELATION_LABELS[r.relationType] || r.relationType
}

/** 关联记录是双向的：找到"对方"需求 id */
function relatedIdOf(r: RelationItem): number {
  return r.demandId === demandId ? r.relatedDemandId : r.demandId
}

function relationDemandNo(r: RelationItem): string {
  return relatedDemands.value.get(relatedIdOf(r))?.demandNo || `#${relatedIdOf(r)}`
}

function relationTitle(r: RelationItem): string {
  return relatedDemands.value.get(relatedIdOf(r))?.title || ''
}

function goRelated(r: RelationItem) {
  const target = relatedIdOf(r)
  if (target && target !== demandId) {
    router.push(`/demand/detail/${target}`).then(() => window.location.reload())
  }
}

async function loadAll() {
  loading.value = true
  try {
    const [d, t] = await Promise.all([getDemand(demandId), getTransitions(demandId)])
    detail.value = d
    transitions.value = t
    // 并行加载协作数据（失败不阻塞主信息）
    await Promise.allSettled([
      listSolutions(demandId).then((v) => {
        solutions.value = v
        if (v.length && !activeSolutionTab.value) {
          // 默认选中当前生效版本（已通过）或最新版本
          const approved = v.find((s) => s.status === 'APPROVED')
          activeSolutionTab.value = String((approved || v[v.length - 1]).id)
        }
      }),
      listReviews(demandId).then((v) => (reviews.value = v)),
      listComments(demandId).then((v) => (comments.value = v)),
      listEfforts(demandId).then((v) => (efforts.value = v)),
      effortSummary(demandId).then((v) => (summary.value = v)),
      listRelations(demandId).then(async (v) => {
        relations.value = v
        // 拉取关联需求编号（逐条查详情较重，用关键字分页按 id 过滤不可行；用详情接口数量少可接受）
        for (const r of v) {
          const rid = relatedIdOf(r)
          if (!relatedDemands.value.has(rid)) {
            try {
              const rd = await getDemand(rid)
              relatedDemands.value.set(rid, {
                id: rd.demand.id,
                demandNo: rd.demand.demandNo,
                title: rd.demand.title
              } as DemandListItem)
            } catch {
              relatedDemands.value.set(rid, { id: rid, demandNo: `#${rid}`, title: '' } as DemandListItem)
            }
          }
        }
      })
    ])
  } finally {
    loading.value = false
  }
}

function resetOpForm() {
  opForm.reason = ''
  opForm.comment = ''
}

async function runOp(fn: () => Promise<unknown>, successMsg: string, closeDlg?: keyof typeof dlg) {
  opLoading.value = true
  try {
    await fn()
    ElMessage.success(successMsg)
    if (closeDlg) {
      dlg[closeDlg] = false
    }
    resetOpForm()
    await loadAll()
    notifyStore.refresh()
  } finally {
    opLoading.value = false
  }
}

/* ---------- 各操作 ---------- */

function onWithdraw() {
  runOp(() => withdrawDemand(demandId, opForm.reason), '需求已撤销', 'withdraw')
}

function openResubmit() {
  const d = detail.value!
  opForm.title = d.demand.title
  opForm.content = d.demand.content
  opForm.urgency = d.demand.urgency
  opForm.expectDeliveryAt = d.demand.expectDeliveryAt || undefined
  dlg.resubmit = true
}

function onResubmit() {
  runOp(
    () =>
      resubmitDemand(demandId, {
        title: opForm.title,
        content: opForm.content,
        urgency: opForm.urgency,
        expectDeliveryAt: opForm.expectDeliveryAt
      }),
    '已重新提交',
    'resubmit'
  )
}

function onAccept() {
  runOp(() => acceptDemand(demandId, opForm.comment || undefined), '已受理，进入需求池', 'accept')
}

function onReturn() {
  runOp(() => returnDemand(demandId, opForm.comment), '已退回提报人补充', 'returnBack')
}

function onClose() {
  runOp(() => closeDemand(demandId, opForm.reason), '需求已关闭', 'close')
}

function openAssign() {
  opForm.assigneeId = null
  dlg.assign = true
}

function onAssign() {
  runOp(() => assignDemand(demandId, opForm.assigneeId!, opForm.comment || undefined), '分派成功', 'assign')
}

async function onClaim() {
  await ElMessageBox.confirm('确认领取该需求？领取后进入分析阶段。', '领取确认', { type: 'info' })
  runOp(() => claimDemand(demandId), '领取成功，开始分析')
}

function onChangeType() {
  runOp(() => changeDemandType(demandId, opForm.newTypeCode, opForm.comment || undefined), '类型已修正', 'changeType')
}

async function onStart() {
  await ElMessageBox.confirm('确认开始处理该需求？', '提示', { type: 'info' })
  runOp(() => startDemand(demandId), '已开始处理')
}

function onHold() {
  runOp(() => holdDemand(demandId, opForm.reason), '需求已挂起', 'hold')
}

async function onResume() {
  await ElMessageBox.confirm('确认恢复处理该需求？', '提示', { type: 'info' })
  runOp(() => resumeDemand(demandId), '需求已恢复')
}

async function onSubmitAcceptance() {
  await ElMessageBox.confirm('确认提交验收？提交后提报人将收到验收提醒。', '提交验收', { type: 'info' })
  runOp(() => submitAcceptance(demandId), '已提交验收')
}

function onAcceptanceReview() {
  runOp(
    () =>
      acceptanceReview(demandId, {
        conclusion: opForm.conclusion,
        qualityScore: opForm.conclusion === 'PASS' ? opForm.qualityScore : undefined,
        satisfactionScore: opForm.conclusion === 'PASS' ? opForm.satisfactionScore : undefined,
        comment: opForm.comment || undefined
      }),
    opForm.conclusion === 'PASS' ? '验收通过，需求已归档' : '已打回整改',
    'acceptance'
  )
}

/* ---------- 方案 ---------- */

function openSolutionEdit(s?: SolutionItem) {
  if (s) {
    opForm.solutionId = s.id
    opForm.solutionVersion = s.version
    opForm.specContent = s.specContent || ''
    opForm.solutionContent = s.solutionContent || ''
    opForm.planDeliveryAt = s.planDeliveryAt || undefined
    opForm.remark = s.remark || ''
  } else {
    opForm.solutionId = null
    opForm.solutionVersion = 0
    opForm.specContent = ''
    opForm.solutionContent = ''
    opForm.planDeliveryAt = undefined
    opForm.remark = ''
  }
  dlg.solution = true
}

async function onSaveSolution(submitReview: boolean) {
  opLoading.value = true
  try {
    let saved: SolutionItem
    const payload = {
      specContent: opForm.specContent || undefined,
      solutionContent: opForm.solutionContent || undefined,
      planDeliveryAt: opForm.planDeliveryAt || undefined,
      remark: opForm.remark || undefined
    }
    if (opForm.solutionId) {
      saved = await updateSolution(opForm.solutionId, payload)
    } else {
      saved = await saveSolution({ demandId, ...payload })
    }
    if (submitReview) {
      await submitSolutionReview(saved.id)
      ElMessage.success('方案已提交评审')
    } else {
      ElMessage.success('方案草稿已保存')
    }
    dlg.solution = false
    await loadAll()
  } finally {
    opLoading.value = false
  }
}

function onSubmitSolutionReview(s: SolutionItem) {
  runOp(() => submitSolutionReview(s.id), `方案 V${s.version} 已提交评审`)
}

function onReview() {
  // 评审对象：当前 REVIEWING 状态的最新方案
  const target = [...solutions.value].reverse().find((s) => s.status === 'REVIEWING')
  if (!target) {
    ElMessage.warning('当前没有待评审的方案版本')
    return
  }
  runOp(
    () => reviewSolution(target.id, { conclusion: opForm.conclusion, comment: opForm.comment || undefined }),
    opForm.conclusion === 'PASS' ? '评审已通过' : '已打回',
    'review'
  )
}

/* ---------- 工时 ---------- */

function onAddEffort() {
  runOp(
    () =>
      addEffort({
        demandId,
        workDate: opForm.workDate,
        hours: opForm.hours,
        description: opForm.description || undefined
      }),
    '工时已提交',
    'effort'
  )
}

/* ---------- 评论 ---------- */

async function onAddComment() {
  commenting.value = true
  try {
    await addComment({
      demandId,
      content: commentInput.value.trim(),
      mentionedUserIds: mentionIds.value.length ? mentionIds.value : undefined
    })
    commentInput.value = ''
    mentionIds.value = []
    comments.value = await listComments(demandId)
    notifyStore.refresh()
  } finally {
    commenting.value = false
  }
}

/* ---------- 关联 / 拆分 ---------- */

let searchTimer: ReturnType<typeof setTimeout> | null = null
function onSearchRelated() {
  if (searchTimer) {
    clearTimeout(searchTimer)
  }
  searchTimer = setTimeout(async () => {
    if (!opForm.relatedKeyword.trim()) {
      relatedOptions.value = []
      return
    }
    const data = await pageDemands({ current: 1, size: 10, keyword: opForm.relatedKeyword.trim() })
    relatedOptions.value = data.records.filter((d) => d.id !== demandId)
  }, 300)
}

function onAddRelation() {
  runOp(
    () => addRelation({ demandId, relatedDemandId: opForm.relatedDemandId!, relationType: opForm.relationType }),
    '关联成功',
    'relate'
  )
}

function openSplit() {
  opForm.title = ''
  opForm.content = ''
  opForm.urgency = detail.value?.demand.urgency || 'NORMAL'
  dlg.split = true
}

function onSplit() {
  runOp(
    () => splitDemand(demandId, { title: opForm.title, content: opForm.content, urgency: opForm.urgency }),
    '子需求已创建',
    'split'
  )
}

/* ---------- 附件 ---------- */

async function onPreview(att: AttachmentItem) {
  previewUrl.value = await previewAttachmentUrl(att.id)
  previewName.value = att.fileName
  previewVisible.value = true
}

function onDownload(att: AttachmentItem) {
  downloadAttachment(att.id, att.fileName)
}

onMounted(async () => {
  const [users, types] = await Promise.all([listAllUsers(), listActiveTypes()])
  allUsers.value = users
  typeList.value = types
  await loadAll()
})
</script>

<style scoped>
.mb16 {
  margin-bottom: 16px;
}

.head-card :deep(.el-card__body) {
  padding: 16px 20px;
}

.head-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.demand-title {
  font-size: 18px;
  font-weight: 700;
}

.head-sub {
  margin-top: 6px;
}

.action-bar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.action-bar .el-button + .el-button {
  margin-left: 0;
}

.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.pre-wrap {
  white-space: pre-wrap;
  word-break: break-word;
}

.att-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

.att-name {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tl-title {
  font-size: 14px;
}

.tl-comment {
  margin-top: 4px;
  font-size: 13px;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-light);
  border-radius: 6px;
  padding: 6px 10px;
  display: inline-block;
}

.kv {
  display: grid;
  grid-template-columns: 90px 1fr;
  row-gap: 10px;
  font-size: 13.5px;
  margin: 0;
}

.kv dt {
  color: var(--el-text-color-secondary);
}

.kv dd {
  margin: 0;
  color: var(--el-text-color-primary);
}

.comment-item {
  padding: 10px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.comment-content {
  margin-top: 4px;
  font-size: 13.5px;
  white-space: pre-wrap;
}

.comment-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}

.review-list {
  margin-top: 12px;
  border-top: 1px dashed var(--el-border-color);
  padding-top: 10px;
}

.review-item {
  padding: 6px 0;
  font-size: 13px;
}

.effort-summary {
  margin-top: 10px;
}

.relation-item {
  padding: 6px 0;
  font-size: 13px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}
</style>
