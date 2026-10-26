# Quản lý quảng cáo Siêu Nét — chạy như một ứng dụng (cửa sổ riêng, không có thanh trình duyệt).
# Đọc / ghi ads.json và ảnh trong repo quangcao, nút "Đăng lên web" = git commit + push.
# Chỉ nghe trên 127.0.0.1, mỗi lần chạy có token riêng; đóng cửa sổ app là tự tắt.
param(
    [string]$Repo = (Split-Path $PSScriptRoot -Parent),
    [int]$Port = 8765
)
$ErrorActionPreference = 'Continue'
$html = Join-Path $PSScriptRoot 'ads-manager.html'
$token = [guid]::NewGuid().ToString('N')
$MaxImage = 6MB
$Types = @{ '.jpg' = 'image/jpeg'; '.jpeg' = 'image/jpeg'; '.png' = 'image/png'; '.webp' = 'image/webp'; '.gif' = 'image/gif' }

if (-not (Test-Path (Join-Path $Repo '.git'))) {
    Add-Type -AssemblyName PresentationFramework
    [void][Windows.MessageBox]::Show("Không thấy repo quảng cáo tại $Repo`nChạy lại với: -Repo <thư mục repo quangcao>", 'Quản lý quảng cáo')
    exit 1
}

$l = New-Object Net.HttpListener
$l.Prefixes.Add("http://127.0.0.1:$Port/")
try { $l.Start() } catch {
    Add-Type -AssemblyName PresentationFramework
    [void][Windows.MessageBox]::Show("Không mở được cổng $Port (app đang chạy rồi?).", 'Quản lý quảng cáo')
    exit 1
}

$url = "http://127.0.0.1:$Port/?t=$token"
$browser = @(
    "$env:ProgramFiles (x86)\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "$env:ProgramFiles (x86)\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
$proc = $null
if ($browser) {
    # hồ sơ riêng để cửa sổ app là một tiến trình riêng: đóng cửa sổ thì biết mà tắt máy chủ
    $profileDir = Join-Path $env:LOCALAPPDATA 'SieuNetAdsManager\profile'
    $proc = Start-Process $browser -PassThru -ArgumentList "--user-data-dir=`"$profileDir`"", "--app=$url",
        '--window-size=1200,860', '--no-first-run', '--no-default-browser-check'
} else {
    Start-Process $url
}

function Send($ctx, $body, [string]$type, [int]$code = 200) {
    $bytes = if ($body -is [byte[]]) { $body } else { [Text.Encoding]::UTF8.GetBytes([string]$body) }
    $ctx.Response.StatusCode = $code
    $ctx.Response.ContentType = if ($type -like 'image/*') { $type } else { "$type; charset=utf-8" }
    $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    $ctx.Response.Close()
}
function Safe-Name([string]$n) {
    if ($n -notmatch '^[\w\-]+\.[A-Za-z]{3,4}$') { return $null }
    if (-not $Types.ContainsKey([IO.Path]::GetExtension($n).ToLower())) { return $null }
    return $n
}
function Git-Out([string[]]$gitArgs) {
    $o = & git -C $Repo @gitArgs 2>&1 | ForEach-Object { "$_" }
    return @{ code = $LASTEXITCODE; text = ($o -join "`n") }
}

$task = $null
while ($l.IsListening) {
    if ($null -eq $task) { $task = $l.GetContextAsync() }
    if (-not $task.Wait(500)) {
        if ($proc -and $proc.HasExited) { break }
        continue
    }
    $ctx = $task.Result
    $task = $null
    $req = $ctx.Request
    $path = $req.Url.AbsolutePath
    $authed = ($req.Headers['X-Token'] -eq $token) -or ($req.QueryString['t'] -eq $token)
    try {
        if ($req.HttpMethod -eq 'GET' -and $path -eq '/') {
            Send $ctx ([IO.File]::ReadAllText($html, [Text.Encoding]::UTF8)) 'text/html'
        }
        elseif (-not $authed) { Send $ctx 'Not found' 'text/plain' 404 }
        elseif ($req.HttpMethod -eq 'GET' -and $path -eq '/api/ads') {
            $p = Join-Path $Repo 'ads.json'
            $text = if (Test-Path $p) { [IO.File]::ReadAllText($p, [Text.Encoding]::UTF8) } else { '' }
            Send $ctx $text 'application/json'
        }
        elseif ($req.HttpMethod -eq 'PUT' -and $path -eq '/api/ads') {
            $sr = New-Object IO.StreamReader($req.InputStream, [Text.Encoding]::UTF8)
            $body = $sr.ReadToEnd()
            $null = $body | ConvertFrom-Json            # từ chối JSON hỏng
            [IO.File]::WriteAllText((Join-Path $Repo 'ads.json'), $body, (New-Object Text.UTF8Encoding $false))
            Send $ctx '{"ok":true}' 'application/json'
        }
        elseif ($req.HttpMethod -eq 'PUT' -and $path -eq '/api/image') {
            $name = Safe-Name $req.QueryString['name']
            if (-not $name) { Send $ctx '{"ok":false}' 'application/json' 400 }
            else {
                $ms = New-Object IO.MemoryStream
                $req.InputStream.CopyTo($ms)
                if ($ms.Length -gt $MaxImage -or $ms.Length -eq 0) { Send $ctx '{"ok":false}' 'application/json' 413 }
                else {
                    [IO.File]::WriteAllBytes((Join-Path $Repo $name), $ms.ToArray())
                    Send $ctx '{"ok":true}' 'application/json'
                }
            }
        }
        elseif ($req.HttpMethod -eq 'GET' -and $path -like '/img/*') {
            $name = Safe-Name ([Uri]::UnescapeDataString($path.Substring(5)))
            $p = if ($name) { Join-Path $Repo $name } else { $null }
            if ($p -and (Test-Path $p)) {
                Send $ctx ([IO.File]::ReadAllBytes($p)) $Types[[IO.Path]::GetExtension($name).ToLower()]
            } else { Send $ctx 'Not found' 'text/plain' 404 }
        }
        elseif ($req.HttpMethod -eq 'POST' -and $path -eq '/publish') {
            $log = @()
            $a = Git-Out @('add', '-A'); $log += $a.text
            $d = Git-Out @('diff', '--cached', '--quiet')
            if ($d.code -eq 0) {
                $res = @{ ok = $true; output = 'Không có thay đổi mới để đăng.' }
            } else {
                $c = Git-Out @('commit', '-q', '-m', ('Cap nhat quang cao ' + (Get-Date -Format 'yyyy-MM-dd HH:mm')))
                $log += $c.text
                $p = Git-Out @('push')
                $log += $p.text
                $res = @{ ok = ($c.code -eq 0 -and $p.code -eq 0); output = (($log | Where-Object { $_ }) -join "`n") }
            }
            Send $ctx ($res | ConvertTo-Json -Compress) 'application/json'
        }
        else { Send $ctx 'Not found' 'text/plain' 404 }
    } catch {
        try { Send $ctx ('{"ok":false,"output":"' + ($_.Exception.Message -replace '["\\\r\n]', ' ') + '"}') 'application/json' 500 } catch {}
    }
}
$l.Stop()
