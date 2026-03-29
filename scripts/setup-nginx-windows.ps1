param(
    [string]$NginxVersion = "1.29.3",
    [string]$NginxRoot = "C:\nginx",
    [string]$ListenPort = "8080",
    [string]$WsgiHost = "127.0.0.1",
    [string]$WsgiPort = "8000",
    [string]$StorageRoot,
    [string]$RepoRoot,
    [switch]$SkipDownload,
    [switch]$NoPrompt
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-LastExitCode {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

function Prompt-Default {
    param(
        [string]$Message,
        [string]$Default
    )

    $raw = Read-Host "$Message [$Default]"
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $Default
    }
    return $raw.Trim()
}

function To-NginxPath {
    param([string]$PathValue)
    return ($PathValue -replace "\\", "/")
}

if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}

$RepoRoot = (Resolve-Path $RepoRoot).Path

if (-not $StorageRoot) {
    $StorageRoot = Join-Path $RepoRoot "src\storage"
}

if (-not $NoPrompt) {
    Write-Host ""
    Write-Host "FANIC nginx setup for Windows"
    Write-Host "This installs nginx, serves /cbz, /fanart, and /static from storage, and proxies all other routes to WSGI."
    Write-Host ""

    $NginxVersion = Prompt-Default -Message "nginx version" -Default $NginxVersion
    $NginxRoot = Prompt-Default -Message "nginx install directory" -Default $NginxRoot
    $ListenPort = Prompt-Default -Message "local listen port" -Default $ListenPort
    $WsgiHost = Prompt-Default -Message "WSGI host" -Default $WsgiHost
    $WsgiPort = Prompt-Default -Message "WSGI port" -Default $WsgiPort
    $RepoRoot = Prompt-Default -Message "repo root" -Default $RepoRoot
    $StorageRoot = Prompt-Default -Message "storage root" -Default $StorageRoot

    $downloadAnswer = Prompt-Default -Message "download or refresh nginx binaries? (yes/no)" -Default "yes"
    $SkipDownload = $downloadAnswer.ToLowerInvariant() -ne "yes"
}

$RepoRoot = (Resolve-Path $RepoRoot).Path
$StorageRoot = (Resolve-Path $StorageRoot).Path
$CbzDir = Join-Path $StorageRoot "cbz"
$DynamicStaticDir = Join-Path $StorageRoot "static"
$FanartDir = Join-Path $StorageRoot "fanart"
if (-not (Test-Path $CbzDir)) {
    throw "Expected cbz file directory was not found: $CbzDir"
}
if (-not (Test-Path $DynamicStaticDir)) {
    throw "Expected static file directory was not found: $DynamicStaticDir"
}
if (-not (Test-Path $FanartDir)) {
    throw "Expected fanart file directory was not found: $FanartDir"
}

$nginxZipUrl = "https://nginx.org/download/nginx-$NginxVersion.zip"
$nginxZipPath = Join-Path $env:TEMP "nginx-$NginxVersion.zip"
$extractRoot = Join-Path $env:TEMP "nginx-$NginxVersion"
$extractedDir = Join-Path $extractRoot "nginx-$NginxVersion"

if (-not $SkipDownload) {
    Write-Host "Downloading nginx from $nginxZipUrl"
    Invoke-WebRequest -Uri $nginxZipUrl -OutFile $nginxZipPath

    if (Test-Path $extractRoot) {
        Remove-Item -Path $extractRoot -Recurse -Force
    }

    Expand-Archive -Path $nginxZipPath -DestinationPath $extractRoot -Force

    if (-not (Test-Path $extractedDir)) {
        throw "Expanded nginx directory not found: $extractedDir"
    }

    if (Test-Path $NginxRoot) {
        Write-Host "Removing existing nginx directory: $NginxRoot"
        Remove-Item -Path $NginxRoot -Recurse -Force
    }

    Write-Host "Installing nginx to $NginxRoot"
    Move-Item -Path $extractedDir -Destination $NginxRoot
}

$nginxExe = Join-Path $NginxRoot "nginx.exe"
if (-not (Test-Path $nginxExe)) {
    throw "nginx executable not found at $nginxExe. Re-run without -SkipDownload or fix -NginxRoot."
}

$confDir = Join-Path $NginxRoot "conf"
if (-not (Test-Path $confDir)) {
    throw "nginx conf directory not found at $confDir"
}

$confPath = Join-Path $confDir "nginx.conf"
if (Test-Path $confPath) {
    $backupPath = "$confPath.bak.$(Get-Date -Format yyyyMMddHHmmss)"
    Copy-Item -Path $confPath -Destination $backupPath -Force
    Write-Host "Backed up existing nginx.conf to $backupPath"
}

$dynamicPathNginx = To-NginxPath -PathValue ((Resolve-Path $DynamicStaticDir).Path)
$cbzPathNginx = To-NginxPath -PathValue ((Resolve-Path $CbzDir).Path)
$fanartPathNginx = To-NginxPath -PathValue ((Resolve-Path $FanartDir).Path)
$nginxPrefix = To-NginxPath -PathValue ((Resolve-Path $NginxRoot).Path)
if (-not $nginxPrefix.EndsWith("/")) {
    $nginxPrefix = "$nginxPrefix/"
}

$nginxConfig = @"
worker_processes  1;

error_log  logs/error.log;
pid        logs/nginx.pid;

events {
    worker_connections  1024;
}

http {
    include       mime.types;
    default_type  application/octet-stream;

    sendfile        on;
    keepalive_timeout  65;

    server {
        listen       127.0.0.1:$ListenPort;
        server_name  localhost;

        error_page 502 503 504 =200 /upstream-unavailable.html;

        location = /upstream-unavailable.html {
            internal;
            root /var/www/fanic-errors;
            default_type text/html;
            add_header Cache-Control "no-store" always;
        }

        location ~* ^/(?:fanic\.db|storage/|.*\.(?:db|sqlite|sqlite3))$ {
            return 404;
        }

        location = /robots.txt {
            default_type text/plain;
            add_header X-Robots-Tag "noindex, nofollow, noarchive" always;
            return 200 "User-agent: *\nDisallow: /\n";
        }

        location /static/ {
            alias $dynamicPathNginx/;
            try_files `$uri =404;
            access_log off;
            add_header Cache-Control "public, max-age=31536000, immutable";
        }

        location /cbz/ {
            alias $cbzPathNginx/;
            try_files `$uri =404;
            access_log off;
        }

        location /fanart/images/ {
            alias $fanartPathNginx/;
            try_files `$uri =404;
            access_log off;
        }

        location /fanart/thumbs/ {
            alias $fanartPathNginx/;
            try_files `$uri =404;
            access_log off;
        }

        location / {
            proxy_pass http://${WsgiHost}:${WsgiPort};
            proxy_http_version 1.1;
            proxy_intercept_errors on;
            proxy_set_header Host `$host;
            proxy_set_header X-Real-IP `$remote_addr;
            proxy_set_header X-Forwarded-For `$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto `$scheme;
        }
    }
}
"@

[System.IO.File]::WriteAllText(
    $confPath,
    $nginxConfig,
    [System.Text.UTF8Encoding]::new($false)
)
Write-Host "Wrote nginx config to $confPath"

Write-Host "Validating nginx config"
& $nginxExe -t -p $nginxPrefix -c conf/nginx.conf
Assert-LastExitCode -Step "nginx config validation"

$running = Get-Process nginx -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "Reloading nginx"
    & $nginxExe -s reload -p $nginxPrefix -c conf/nginx.conf
    Assert-LastExitCode -Step "nginx reload"
} else {
    Write-Host "Starting nginx"
    $startArgs = @(
        "-p"
        $nginxPrefix
        "-c"
        "conf/nginx.conf"
    )
    $null = Start-Process -FilePath $nginxExe -ArgumentList $startArgs -WindowStyle Hidden -PassThru
    Start-Sleep -Milliseconds 800
    $started = Get-Process nginx -ErrorAction SilentlyContinue
    if (-not $started) {
        throw "nginx start did not create a running nginx process"
    }
}

Write-Host ""
Write-Host "Setup complete"
Write-Host "nginx root: $NginxRoot"
Write-Host "serving /cbz from: $CbzDir"
Write-Host "serving /static from: $DynamicStaticDir"
Write-Host "serving /fanart from: $FanartDir"
Write-Host "proxying dynamic routes to: http://${WsgiHost}:${WsgiPort}"
Write-Host "open: http://127.0.0.1:$ListenPort"
Write-Host ""
Write-Host "Common commands:"
Write-Host "  $nginxExe -s reload -p $nginxPrefix -c conf/nginx.conf"
Write-Host "  $nginxExe -s stop   -p $nginxPrefix -c conf/nginx.conf"
