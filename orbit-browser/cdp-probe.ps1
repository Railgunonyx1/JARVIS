$js = 'JSON.stringify({ sbDot: document.getElementById("sbDot")?.className, sbTitleLS: document.querySelector(".sb-title")?.style?.letterSpacing, composerBg: getComputedStyle(document.querySelector(".sb-composer-box")).backgroundImage, composerBorder: getComputedStyle(document.querySelector(".sb-composer-box")).borderColor, modelSelectVal: document.getElementById("settingsModelSelect")?.value, builderLimitVal: document.getElementById("settingsBuilderLimit")?.value, modelChipLabel: document.getElementById("sbModelName")?.textContent, dotAnim: document.getElementById("sbDot")?.style?.animation, textareaBg: getComputedStyle(document.querySelector(".sb-composer-box textarea")).background, textareaColor: getComputedStyle(document.querySelector(".sb-composer-box textarea")).color })'
$port = 9222
$url = "$env:COMPUTERNAME`:$port`/json"
$wc = New-Object System.Net.WebClient
try { $dev = $wc.DownloadString($url) | ConvertFrom-Json } catch { Write-Host "NO CDP on $port"; exit 1 }
$wsUrl = $dev.webSocketDebuggerUrl
$ws = New-Object System.Net.WebSockets.ClientWebSocket
$ct = New-Object System.Threading.CancellationTokenSource
$ct.CancelAfter(5000)
$ws.ConnectAsync([Uri]::new($wsUrl), $ct.Token).Wait()
$msg = "{`"id`":1,`"method`":`"Runtime.evaluate`",`"params`":{`"expression`":`"$js`",`"returnByValue`":true}}"
$bytes = [System.Text.Encoding]::UTF8.GetBytes($msg)
$ws.SendAsync([System.ArraySegment[byte]]::new($bytes,0,$bytes.Length), 'Text', $true, $ct.Token).Wait()
$buf = [byte[]]::new(1048576)
$ms = New-Object System.IO.MemoryStream
$ct2 = New-Object System.Threading.CancellationTokenSource
$ct2.CancelAfter(8000)
while (-not $ct2.Token.IsCancellationRequested -and $ws.State -eq 'Open') {
  $res = $ws.ReceiveAsync([System.ArraySegment[byte]]::new($buf,0,$buf.Length), $ct2.Token).Result
  if ($res.Count -gt 0) { $ms.Write($buf,0,$res.Count) }
  if ($res.EndOfMessage) { break }
}
$ws.CloseAsync('NormalClosure', "", $ct.Token).Wait()
$out = $ms.ToString()
Out-File -InputObject $out -FilePath "$env:TEMP/cdp.out.txt" -Encoding utf8
$obj = $out | ConvertFrom-Json
Write-Host "sbDot=$($obj.sbDot)"
Write-Host "sbTitleLS=$($obj.sbTitleLS)"
Write-Host "composerBg=$($obj.composerBg)"
Write-Host "composerBorder=$($obj.composerBorder)"
Write-Host "modelSelect=$($obj.modelSelectVal)"
Write-Host "builderLimit=$($obj.builderLimitVal)"
Write-Host "modelChipLabel=$($obj.modelChipLabel)"
Write-Host "dotAnim=$($obj.dotAnim)"
Write-Host "textareaBg=$($obj.textareaBg)"
Write-Host "textareaColor=$($obj.textareaColor)"
