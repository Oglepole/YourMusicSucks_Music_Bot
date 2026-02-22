Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$botScript = Join-Path $scriptDir "bot.py"
$outLog = Join-Path $scriptDir "bot.out"
$errLog = Join-Path $scriptDir "bot.err"
$pythonExe = "C:\Users\markf\AppData\Local\Programs\Python\Python312\python.exe"

function Get-BotProcesses {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -eq "python.exe" -and
            $_.CommandLine -match [regex]::Escape("bot.py")
        }
}

function Start-Bot {
    if (!(Test-Path $botScript)) {
        [System.Windows.Forms.MessageBox]::Show("bot.py not found in $scriptDir", "Error")
        return
    }

    $running = Get-BotProcesses
    if ($running) {
        [System.Windows.Forms.MessageBox]::Show("Bot is already running.", "Info")
        return
    }

    $exe = if (Test-Path $pythonExe) { $pythonExe } else { "python" }
    Start-Process -FilePath $exe `
        -ArgumentList "-u", ".\bot.py" `
        -WorkingDirectory $scriptDir `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog | Out-Null

    Start-Sleep -Milliseconds 800
    $started = Get-BotProcesses
    if ($started) {
        [System.Windows.Forms.MessageBox]::Show("Bot started. PID: $($started[0].ProcessId)", "Success")
    } else {
        [System.Windows.Forms.MessageBox]::Show("Bot did not start. Check bot.err for details.", "Error")
    }
}

function Stop-Bot {
    $running = Get-BotProcesses
    if (!$running) {
        [System.Windows.Forms.MessageBox]::Show("Bot is not running.", "Info")
        return
    }

    foreach ($proc in $running) {
        Stop-Process -Id $proc.ProcessId -Force
    }
    [System.Windows.Forms.MessageBox]::Show("Bot stopped.", "Success")
}

function Show-Status {
    $running = Get-BotProcesses
    if ($running) {
        [System.Windows.Forms.MessageBox]::Show("Bot is running.`nPID: $($running[0].ProcessId)", "Status")
    } else {
        [System.Windows.Forms.MessageBox]::Show("Bot is stopped.", "Status")
    }
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "Discord Music Bot Control"
$form.Size = New-Object System.Drawing.Size(360, 190)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false

$label = New-Object System.Windows.Forms.Label
$label.Text = "Manage bot process"
$label.AutoSize = $true
$label.Location = New-Object System.Drawing.Point(18, 15)
$form.Controls.Add($label)

$startButton = New-Object System.Windows.Forms.Button
$startButton.Text = "Start Bot"
$startButton.Size = New-Object System.Drawing.Size(95, 36)
$startButton.Location = New-Object System.Drawing.Point(20, 55)
$startButton.Add_Click({ Start-Bot })
$form.Controls.Add($startButton)

$stopButton = New-Object System.Windows.Forms.Button
$stopButton.Text = "Stop Bot"
$stopButton.Size = New-Object System.Drawing.Size(95, 36)
$stopButton.Location = New-Object System.Drawing.Point(130, 55)
$stopButton.Add_Click({ Stop-Bot })
$form.Controls.Add($stopButton)

$statusButton = New-Object System.Windows.Forms.Button
$statusButton.Text = "Status"
$statusButton.Size = New-Object System.Drawing.Size(95, 36)
$statusButton.Location = New-Object System.Drawing.Point(240, 55)
$statusButton.Add_Click({ Show-Status })
$form.Controls.Add($statusButton)

$closeButton = New-Object System.Windows.Forms.Button
$closeButton.Text = "Close"
$closeButton.Size = New-Object System.Drawing.Size(95, 30)
$closeButton.Location = New-Object System.Drawing.Point(130, 105)
$closeButton.Add_Click({ $form.Close() })
$form.Controls.Add($closeButton)

[void]$form.ShowDialog()
