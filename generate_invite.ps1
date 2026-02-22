param(
    [Parameter(Mandatory = $true)]
    [string]$ClientId
)

# Scopes: bot + applications.commands
$scopes = "bot%20applications.commands"

# Permissions included:
# View Channels, Send Messages, Read Message History, Embed Links,
# Connect, Speak, Use Voice Activity
$permissions = "36785152"

$url = "https://discord.com/oauth2/authorize?client_id=$ClientId&permissions=$permissions&scope=$scopes"
Write-Output $url
