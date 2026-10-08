﻿$ErrorActionPreference = 'Stop'
$env:NO_PROXY = '127.0.0.1,localhost'
$base = 'http://127.0.0.1:8000/demandhub-api'

function Post-Json($url, $token, $obj) {
  $json = $obj | ConvertTo-Json -Depth 10 -Compress
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
  Invoke-RestMethod -Method Post -Uri $url -Headers @{ Authorization = "Bearer $token" } -ContentType 'application/json; charset=utf-8' -Body $bytes -TimeoutSec 60
}
function Put-Json($url, $token, $obj) {
  $json = $obj | ConvertTo-Json -Depth 10 -Compress
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
  Invoke-RestMethod -Method Put -Uri $url -Headers @{ Authorization = "Bearer $token" } -ContentType 'application/json; charset=utf-8' -Body $bytes -TimeoutSec 30
}

# 1. 登录
$t = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8199/ticket' -ContentType 'application/json' -Body '{"channelUserId":"mvp-admin","name":"管理员"}' -TimeoutSec 5
$login = Invoke-RestMethod -Uri "$base/auth/channel-sso?channel=chuangjinls&ticket=$($t.ticket)" -TimeoutSec 10
$token = $login.data.accessToken
Write-Output "== 1 login ok: userId=$($login.data.user.userId) isAdmin=$($login.data.user.isAdmin)"

# 2. 粘贴大段需求建草稿（A8 原文）
$bigText = '我们部门每天晨会要统计各渠道销量，现在靠人工从三个系统导出再合并，20多个客户经理每人每天花40分钟手工整理，经常出错。希望做一个自动汇总报表，每天8点前把前一交易日各渠道、各产品的销量和保有量推送到部门群里，目标是把晨会准备时间从40分钟降到5分钟，覆盖率提升到100%。承接方是科技中心，受益方是机构业务部全体客户经理。'
$draft = Post-Json "$base/demand" $token @{ demandTypeCode = 'TECH'; title = ''; content = $bigText; clientRequestId = [guid]::NewGuid().ToString('N') }
$demandId = $draft.data.id
Write-Output "== 2 draft created: id=$demandId revision=$($draft.data.revision) changeLogs=$($draft.data.changeLogs.Count) status=$($draft.data.status)"

# 3. 模拟判型确认（H5 判型卡确认 → ext.typeRecognition.confirmed='business'），并先补标题
$upd = Put-Json "$base/demand/$demandId" $token @{ expectedRevision = $draft.data.revision; title = '晨会销量自动汇总报表'; ext = @{ typeRecognition = @{ business = 0.9; confirmed = 'business' } } }
if ($upd.code -ne 0) { Write-Output "== 3 confirm FAILED: $($upd | ConvertTo-Json -Compress)"; exit 1 }
Write-Output "== 3 confirm type saved: revision=$($upd.data.revision)"

# 4. 已确认业务需求但不填 B 区直接提交，应被条件必填拦截
$submit1 = Post-Json "$base/demand/$demandId/submit" $token @{ expectedRevision = $upd.data.revision }
if ($submit1.code -eq 0) {
  Write-Output "== 4 submit WITHOUT B-zone: UNEXPECTED SUCCESS demandNo=$($submit1.data.demandNo)"
} else {
  Write-Output "== 4 submit WITHOUT B-zone blocked as expected: code=$($submit1.code) message=$($submit1.message)"
}

# 5. 补齐 A/B/C/D 必填后提交
$elements = @{
  A = @{ techSubtype = 'DATA_RPT' }
  B = @{ businessGoal = '把晨会准备时间从40分钟降到5分钟，覆盖率提升到100%'; businessBackground = '目前靠人工从三个系统导出再合并，20多个客户经理每人每天花40分钟手工整理，经常出错，因此需要自动化'; businessValue = '影响20多人，每人每天节省约35分钟；不做会持续出错影响晨会决策'; stakeholders = @('机构业务部', '科技中心', '客户经理') }
  C = @{ userRole = '客户经理'; userGoal = '每天8点前自动收到汇总报表'; painPoint = '手工整理耗时且易出错'; useScenario = '交易日晨会前查看各渠道销量' }
  D = @{ functionDescription = '系统自动从三个系统抽取数据，按渠道和产品汇总生成报表并推送到部门群'; inputOutput = '输入三个系统的交易与持仓数据，输出按渠道和产品汇总的报表并推送'; acceptanceCriteria = '每天8点前推送成功率99%以上，与源系统对账误差为0' }
}
$upd2 = Put-Json "$base/demand/$demandId" $token @{ expectedRevision = $upd.data.revision; title = '晨会销量自动汇总报表'; elements = $elements }
if ($upd2.code -ne 0) { Write-Output "== 5 update FAILED: $($upd2 | ConvertTo-Json -Compress -Depth 5)"; exit 1 }
Write-Output "== 5 elements saved: revision=$($upd2.data.revision) zones=$(($upd2.data.elements.PSObject.Properties.Name) -join ',')"
$submit2 = Post-Json "$base/demand/$demandId/submit" $token @{ expectedRevision = $upd2.data.revision }
if ($submit2.code -ne 0) { Write-Output "== 6 submit FAILED: code=$($submit2.code) message=$($submit2.message)"; exit 1 }
Write-Output "== 6 submit WITH full zones: status=$($submit2.data.status) demandNo=$($submit2.data.demandNo)"

# 6. 留痕校验（修改次数 + changeLogs；detail 结构为 data.demand 嵌套）
$detail = Invoke-RestMethod -Uri "$base/demand/$demandId" -Headers @{ Authorization = "Bearer $token" } -TimeoutSec 10
$d = $detail.data.demand
Write-Output "== 7 detail: revision=$($d.revision) changeLogs=$($d.changeLogs.Count) fieldSources=$($d.fieldSources.PSObject.Properties.Name.Count) qualityItems=$($detail.data.quality.Count)"
$d.changeLogs | Select-Object -First 8 | ForEach-Object { Write-Output "   log: $($_.fieldKey) [$($_.source)]" }

# 7. 导出 markdown 分区校验
$md = Invoke-RestMethod -Uri "$base/demand/$demandId/export.md" -Headers @{ Authorization = "Bearer $token" } -TimeoutSec 10
$mdText = ($md | Out-String)
Write-Output "== 8 export.md: hasA8=$($mdText.Contains('原始提报文本')) hasB=$($mdText.Contains('业务需求')) hasE=$($mdText.Contains('变更留痕')) len=$($mdText.Length)"
