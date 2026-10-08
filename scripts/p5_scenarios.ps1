﻿$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:NO_PROXY = '127.0.0.1,localhost'
$base = 'http://127.0.0.1:8000/demandhub-api'
$script:results = @()

# Starlette JSONResponse 不带 charset，PS5.1 默认按 Latin-1 解码会乱码，统一按 UTF-8 字节解码
function Send-Api($method, $url, $token, $obj = $null) {
  $params = @{ Method = $method; Uri = $url; TimeoutSec = 60; UseBasicParsing = $true }
  if ($token) { $params.Headers = @{ Authorization = "Bearer $token" } }
  if ($null -ne $obj) {
    $params.ContentType = 'application/json; charset=utf-8'
    $params.Body = [System.Text.Encoding]::UTF8.GetBytes(($obj | ConvertTo-Json -Depth 10 -Compress))
  }
  $r = Invoke-WebRequest @params
  [System.Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray()) | ConvertFrom-Json
}
function Login($userId) {
  $t = Send-Api Post 'http://127.0.0.1:8199/ticket' $null @{ channelUserId = $userId; name = 'P5验收用户' }
  (Send-Api Get "$base/auth/channel-sso?channel=chuangjinls&ticket=$($t.ticket)" $null).data.accessToken
}
function New-Draft($token, $content) { (Send-Api Post "$base/demand" $token @{ demandTypeCode = 'TECH'; content = $content; clientRequestId = [guid]::NewGuid().ToString('N') }).data }
function New-Session($token, $demandId) { (Send-Api Post "$base/agent/session" $token @{ demandId = $demandId }).data }
function Chat($token, $demandId, $sessionId, $revision, $message) {
  (Send-Api Post "$base/agent/guide/chat" $token @{ demandId = $demandId; sessionId = $sessionId; revision = $revision; message = $message; requestId = [guid]::NewGuid().ToString('N') }).data
}
function Check($name, $cond, $detail) { $script:results += [pscustomobject]@{ Name = $name; Pass = [bool]$cond; Detail = $detail } }

$bigText = '我们部门每天晨会要统计各渠道销量，现在靠人工从三个系统导出再合并，20多个客户经理每人每天花40分钟手工整理，经常出错。希望做一个自动汇总报表，每天8点前把前一交易日各渠道、各产品的销量和保有量推送到部门群里，目标是把晨会准备时间从40分钟降到5分钟，覆盖率提升到100%。承接方是科技中心，受益方是机构业务部全体客户经理。'
$fullElements = @{
  A = @{ techSubtype = 'DATA_RPT' }
  B = @{ businessGoal = '把晨会准备时间从40分钟降到5分钟，覆盖率提升到100%'; businessBackground = '目前靠人工从三个系统导出再合并，20多个客户经理每人每天花40分钟手工整理，经常出错，因此需要自动化'; businessValue = '影响20多人，每人每天节省约35分钟；不做会持续出错影响晨会决策'; stakeholders = @('机构业务部', '科技中心', '客户经理') }
  C = @{ userRole = '客户经理'; userGoal = '每天8点前自动收到汇总报表'; painPoint = '手工整理耗时且易出错'; useScenario = '交易日晨会前查看各渠道销量' }
  D = @{ functionDescription = '系统自动从三个系统抽取数据，按渠道和产品汇总生成报表并推送到部门群'; inputOutput = '输入三个系统的交易与持仓数据，输出按渠道和产品汇总的报表并推送'; acceptanceCriteria = '每天8点前推送成功率99%以上，与源系统对账误差为0' }
}

# ===== 场景1：新用户 → 示例填入 → 提交 =====
$u1 = Login("p5s1-$([guid]::NewGuid().ToString('N').Substring(0,8))")
$d1 = New-Draft $u1 $bigText
Check 'S1 新用户建草稿(示例原文)' ($d1.status -eq 'DRAFT' -and $d1.content -eq $bigText) "id=$($d1.id)"
$u1r = Send-Api Put "$base/demand/$($d1.id)" $u1 @{ expectedRevision = $d1.revision; title = '晨会销量自动汇总报表'; elements = $fullElements }
$s1 = Send-Api Post "$base/demand/$($d1.id)/submit" $u1 @{ expectedRevision = $u1r.data.revision }
Check 'S1 提交成功' ($s1.code -eq 0 -and $s1.data.status -eq 'SUBMITTED') "demandNo=$($s1.data.demandNo)"

# ===== 场景2：大段粘贴 → 判型卡 → 确认 → 拆解/A8 → 追问 =====
$u2 = Login("p5s2-$([guid]::NewGuid().ToString('N').Substring(0,8))")
$d2 = New-Draft $u2 ''
$ss2 = New-Session $u2 $d2.id
$c2 = Chat $u2 $d2.id $ss2.id $d2.revision $bigText
$tr = $c2.typeRecognition
Check 'S2 判型卡(business>=0.5未确认)' ($tr -and $tr.business -ge 0.5 -and -not $tr.confirmed) "business=$($tr.business) evidence=$($tr.evidence.business)"
Check 'S2 A8原文完整' ($c2.structured.content -eq $bigText) "len=$($c2.structured.content.Length)/$($bigText.Length)"
Check 'S2 五区已拆解(B1有值)' ($c2.structured.elements.B.businessGoal.Length -gt 0) "B1=$($c2.structured.elements.B.businessGoal)"
Check 'S2 必填空缺被追问' ($c2.missing.Count -gt 0 -and $c2.askedTarget) "asked=$($c2.askedTarget) missing=$($c2.missing.Count)"
$u2r = Send-Api Put "$base/demand/$($d2.id)" $u2 @{ expectedRevision = $c2.revision; ext = @{ typeRecognition = @{ business = $tr.business; confirmed = 'business' } } }
Check 'S2 判型确认落库' ($u2r.code -eq 0) "revision=$($u2r.data.revision)"
$sb2 = Send-Api Post "$base/demand/$($d2.id)/submit" $u2 @{ expectedRevision = $u2r.data.revision }
Check 'S2 B区空缺提交被拦截' ($sb2.code -eq 400 -and $sb2.message -match '未填写') "code=$($sb2.code) msg=$($sb2.message)"

# ===== 场景3：字段级需求 → too_narrow 补全提示 → 补全后继续 =====
$u3 = Login("p5s3-$([guid]::NewGuid().ToString('N').Substring(0,8))")
$d3 = New-Draft $u3 ''
$ss3 = New-Session $u3 $d3.id
$c3 = Chat $u3 $d3.id $ss3.id $d3.revision '给持仓报表加个字段，显示基金净值日期'
Check 'S3 字段级收到too_narrow提示' ($c3.granularityHint -and $c3.granularityHint.level -eq 'too_narrow' -and $c3.granularityHint.converge.Length -gt 0) "converge=$($c3.granularityHint.converge)"
$u3r = Send-Api Put "$base/demand/$($d3.id)" $u3 @{ expectedRevision = $c3.revision; elements = @{ C = @{ userRole = '机构业务部客户经理'; useScenario = '客户经理每天晨会前查看各机构持仓与基金净值日期' } } }
$c3b = Chat $u3 $d3.id $ss3.id $u3r.data.revision '已补充使用场景和用户角色，继续'
Check 'S3 补全后提示解除' ($null -eq $c3b.granularityHint) "hint=$($c3b.granularityHint.level)"

# ===== 场景4：战略级需求 → too_broad 分解引导 → 聚焦一条 → 其余存草稿 =====
$u4 = Login("p5s4-$([guid]::NewGuid().ToString('N').Substring(0,8))")
$d4 = New-Draft $u4 ''
$ss4 = New-Session $u4 $d4.id
$c4 = Chat $u4 $d4.id $ss4.id $d4.revision '提升客户回访率到80%'
Check 'S4 战略级收到too_broad分解引导' ($c4.granularityHint -and $c4.granularityHint.level -eq 'too_broad' -and $c4.granularityHint.hint.Length -gt 0) "hint ok"
$u4r = Send-Api Put "$base/demand/$($d4.id)" $u4 @{ expectedRevision = $c4.revision; title = '客户回访话术质检报表'; content = '聚焦子需求：回访话术质检。机构业务部客户经理每周抽查回访录音，按话术合规项打分，目标是把抽检覆盖率从10%提升到50%。'; elements = $fullElements }
$s4 = Send-Api Post "$base/demand/$($d4.id)/submit" $u4 @{ expectedRevision = $u4r.data.revision }
Check 'S4 聚焦子需求提交成功' ($s4.code -eq 0 -and $s4.data.status -eq 'SUBMITTED') "demandNo=$($s4.data.demandNo)"
$d4b = New-Draft $u4 '其余子需求：回访任务自动分配、回访结果看板（待拆解，暂存草稿）'
Check 'S4 其余子需求留存草稿' ($d4b.status -eq 'DRAFT') "id=$($d4b.id)"

# ===== 场景5：对话中修改 B1 → 影响提示 → changeLog 可查 =====
$u5 = Login("p5s5-$([guid]::NewGuid().ToString('N').Substring(0,8))")
$d5 = New-Draft $u5 ''
$ss5 = New-Session $u5 $d5.id
$c5a = Chat $u5 $d5.id $ss5.id $d5.revision $bigText
$b1Before = $c5a.structured.elements.B.businessGoal
$c5b = Chat $u5 $d5.id $ss5.id $c5a.revision 'B1 业务目标改一下：目标是把晨会准备时间从40分钟降到5分钟'
$b1After = $c5b.structured.elements.B.businessGoal
Check 'S5 对话修改定位B1并生效' ($b1After -ne $b1Before -and $b1After -match '5分钟') "B1: $b1Before -> $b1After"
Check 'S5 影响提示(联动确认)' ($c5b.impactHints.Count -gt 0) "hints=$($c5b.impactHints.Count)"
$det5 = Send-Api Get "$base/demand/$($d5.id)" $u5
$log5 = @($det5.data.demand.changeLogs | Where-Object { $_.fieldKey -eq 'elements.B.businessGoal' })
$log5mod = $log5[-1]
Check 'S5 changeLog可查(旧值->新值)' ($log5.Count -ge 2 -and $log5mod.oldValue -eq $b1Before -and $log5mod.newValue -eq $b1After) "logs=$($log5.Count) source=$($log5mod.source)"
Check 'S5 A8原文未被模型改写' ($c5b.structured.content -eq $bigText) "content preserved"

# ===== 场景6：草稿中断 → 列表续报 → 提交 → 详情完整 =====
$u6 = Login("p5s6-$([guid]::NewGuid().ToString('N').Substring(0,8))")
$d6 = New-Draft $u6 $bigText
$mine = Send-Api Get "$base/demand/my?status=DRAFT" $u6
Check 'S6 草稿出现在我的列表' ($mine.data.records.id -contains $d6.id) "total=$($mine.data.total)"
$res6 = Send-Api Get "$base/demand/$($d6.id)" $u6
Check 'S6 续报恢复草稿' ($res6.data.demand.status -eq 'DRAFT' -and $res6.data.demand.content -eq $bigText) "revision=$($res6.data.demand.revision)"
$ss6 = New-Session $u6 $d6.id
$c6 = Chat $u6 $d6.id $ss6.id $res6.data.demand.revision '补充：承接方科技中心，受益方机构业务部客户经理'
$u6r = Send-Api Put "$base/demand/$($d6.id)" $u6 @{ expectedRevision = $c6.revision; title = '晨会销量自动汇总报表'; elements = $fullElements }
$s6 = Send-Api Post "$base/demand/$($d6.id)/submit" $u6 @{ expectedRevision = $u6r.data.revision }
Check 'S6 续报后提交成功' ($s6.code -eq 0 -and $s6.data.status -eq 'SUBMITTED') "demandNo=$($s6.data.demandNo)"
$det6 = Send-Api Get "$base/demand/$($d6.id)" $u6
$dd6 = $det6.data.demand
Check 'S6 详情完整(五区+质量+回放+留痕)' ($dd6.elements.A.techSubtype -and $det6.data.quality.Count -gt 0 -and $det6.data.messages.Count -ge 2 -and $dd6.changeLogs.Count -gt 0 -and $det6.data.standard.type -eq 'TECH') "quality=$($det6.data.quality.Count) msgs=$($det6.data.messages.Count) logs=$($dd6.changeLogs.Count)"

# ===== 汇总 =====
Write-Output ''
$script:results | ForEach-Object { Write-Output ("{0} {1} | {2}" -f $(if ($_.Pass) { 'PASS' } else { 'FAIL' }), $_.Name, $_.Detail) }
$failed = @($script:results | Where-Object { -not $_.Pass })
Write-Output ''
Write-Output ("TOTAL: {0} passed, {1} failed" -f ($script:results.Count - $failed.Count), $failed.Count)
if ($failed.Count -gt 0) { exit 1 }
