$js = 'JSON.stringify({ sbDot: document.getElementById("sbDot")?.className, sbTitleLS: document.querySelector(".sb-title")?.style?.letterSpacing, composerBg: getComputedStyle(document.getElementById("sbInput")?.closest(".sb-composer-box")).backgroundImage, composerBorder: getComputedStyle(document.getElementById("sbInput")?.closest(".sb-composer-box")).borderColor, modelSelectVal: document.getElementById("settingsModelSelect")?.value, builderLimitVal: document.getElementById("settingsBuilderLimit")?.value, modelChipLabel: document.getElementById("sbModelName")?.textContent, dotAnim: document.getElementById("sbDot")?.style?.animation, textareaBg: getComputedStyle(document.querySelector(".sb-composer-box textarea")).background, textareaColor: getComputedStyle(document.querySelector(".sb-composer-box textarea")).color })'
$port = 9222
$url = "http://127.0.0.1:$port/json"
$wc = New-Object System.Net.WebClient
$dev = $wc.DownloadString($url) | ConvertFrom-Json
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
Out-File -InputObject $ms.ToString() -FilePath C:\Users\aayan\AppData\Local\Temp\jv.out.txt -Encoding utf8
Write-Host "DONE"
