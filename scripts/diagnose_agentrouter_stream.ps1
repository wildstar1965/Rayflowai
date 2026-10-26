param(
    [string]$BaseUrl = "https://agentrouter.org/v1",
    [string]$Model = "gpt-6-astra",
    [int]$TimeoutSeconds = 60,
    [int]$RepeatedRequests = 2
)

$ErrorActionPreference = "Stop"

function Get-ConfiguredApiKey {
    foreach ($name in @("CODEX_GATEWAY_API_KEY", "AGENTROUTER_API_KEY")) {
        $value = [Environment]::GetEnvironmentVariable($name, "Process")
        if ($value) {
            return $value
        }
    }

    throw "No configured API key found in CODEX_GATEWAY_API_KEY or AGENTROUTER_API_KEY."
}

function Get-ErrorSummary([string]$Body) {
    if (-not $Body) {
        return "<empty response body>"
    }

    $singleLine = ($Body -replace "\s+", " ").Trim()
    if ($singleLine.Length -gt 300) {
        return $singleLine.Substring(0, 300) + "..."
    }
    return $singleLine
}

function Invoke-ResponsesRequest(
    [System.Net.Http.HttpClient]$Client,
    [string]$ApiKey,
    [string]$Prompt,
    [bool]$Stream
) {
    $payload = @{
        model  = $Model
        input  = $Prompt
        stream = $Stream
    } | ConvertTo-Json -Compress

    $request = [System.Net.Http.HttpRequestMessage]::new(
        [System.Net.Http.HttpMethod]::Post,
        "$($BaseUrl.TrimEnd('/'))/responses"
    )
    $request.Headers.Authorization = [System.Net.Http.Headers.AuthenticationHeaderValue]::new("Bearer", $ApiKey)
    $request.Headers.Add("originator", "codex_cli_rs")
    $request.Headers.UserAgent.ParseAdd("codex_cli_rs/0.163.0")
    $request.Headers.Accept.ParseAdd($(if ($Stream) { "text/event-stream" } else { "application/json" }))
    $request.Content = [System.Net.Http.StringContent]::new(
        $payload,
        [System.Text.Encoding]::UTF8,
        "application/json"
    )

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $response = $Client.SendAsync(
            $request,
            [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead
        ).GetAwaiter().GetResult()
        $headersMs = $stopwatch.ElapsedMilliseconds

        if (-not $response.IsSuccessStatusCode) {
            $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            return [pscustomobject]@{
                Status       = [int]$response.StatusCode
                HeadersMs    = $headersMs
                TotalMs      = $stopwatch.ElapsedMilliseconds
                Events       = @()
                Terminal     = "http_error"
                Error        = Get-ErrorSummary $body
            }
        }

        if (-not $Stream) {
            $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            $json = $body | ConvertFrom-Json
            return [pscustomobject]@{
                Status       = [int]$response.StatusCode
                HeadersMs    = $headersMs
                TotalMs      = $stopwatch.ElapsedMilliseconds
                Events       = @($json.type)
                Terminal     = if ($json.status) { $json.status } else { "json_response" }
                Error        = $null
            }
        }

        $reader = [System.IO.StreamReader]::new(
            $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        )
        $eventTypes = [System.Collections.Generic.List[string]]::new()
        $terminal = $null
        $eventData = [System.Collections.Generic.List[string]]::new()
        $streamError = $null

        while ($null -ne ($line = $reader.ReadLine())) {
            if ($line.StartsWith("event:")) {
                $eventType = $line.Substring(6).Trim()
                if ($eventType) {
                    $eventTypes.Add($eventType)
                    if ($eventType -in @("response.completed", "response.failed", "error")) {
                        $terminal = $eventType
                    }
                }
            } elseif ($line.StartsWith("data:")) {
                $data = $line.Substring(5).Trim()
                if ($data -and $data -ne "[DONE]") {
                    try {
                        $parsed = $data | ConvertFrom-Json
                        if ($parsed.type -and -not $eventTypes.Contains([string]$parsed.type)) {
                            $eventTypes.Add([string]$parsed.type)
                            if ($parsed.type -in @("response.completed", "response.failed", "error")) {
                                $terminal = [string]$parsed.type
                            }
                        }
                        if ($parsed.type -in @("response.failed", "error")) {
                            $errorParts = @()
                            if ($parsed.error.code) {
                                $errorParts += "code=$($parsed.error.code)"
                            }
                            if ($parsed.error.message) {
                                $errorParts += "message=$(Get-ErrorSummary ([string]$parsed.error.message))"
                            } elseif ($parsed.message) {
                                $errorParts += "message=$(Get-ErrorSummary ([string]$parsed.message))"
                            }
                            if ($errorParts.Count) {
                                $streamError = $errorParts -join ";"
                            }
                        }
                    } catch {
                        $eventData.Add("unparseable_data")
                    }
                }
            }
        }

        return [pscustomobject]@{
            Status       = [int]$response.StatusCode
            HeadersMs    = $headersMs
            TotalMs      = $stopwatch.ElapsedMilliseconds
            Events       = @($eventTypes | Select-Object -Unique)
            Terminal     = if ($terminal) { $terminal } else { "stream_closed_before_terminal" }
            Error        = if ($streamError) { $streamError } elseif ($eventData.Count) { $eventData -join "," } else { $null }
        }
    } catch {
        return [pscustomobject]@{
            Status       = $null
            HeadersMs    = $null
            TotalMs      = $stopwatch.ElapsedMilliseconds
            Events       = @()
            Terminal     = "network_or_client_error"
            Error        = Get-ErrorSummary $_.Exception.Message
        }
    } finally {
        $request.Dispose()
    }
}

$uri = [Uri]$BaseUrl
$apiKey = Get-ConfiguredApiKey
$handler = [System.Net.Http.HttpClientHandler]::new()
$client = [System.Net.Http.HttpClient]::new($handler)
$client.Timeout = [TimeSpan]::FromSeconds($TimeoutSeconds)

try {
    Write-Output "endpoint_host=$($uri.Host)"
    Write-Output "endpoint_path=$($uri.AbsolutePath)"
    Write-Output "model=$Model"
    Write-Output "timeout_seconds=$TimeoutSeconds"
    try {
        $dns = [System.Net.Dns]::GetHostAddresses($uri.Host) | Select-Object -ExpandProperty IPAddressToString
        Write-Output "dns=$($dns -join ',')"
    } catch {
        Write-Output "dns_error=$(Get-ErrorSummary $_.Exception.Message)"
    }

    $tests = @(
        @{ Name = "A_minimal_nonstream"; Prompt = "Reply with OK."; Stream = $false },
        @{ Name = "B_minimal_stream"; Prompt = "Reply with OK."; Stream = $true },
        @{ Name = "C_longer_stream"; Prompt = "Give a concise five-bullet checklist for testing an HTTP server-sent events stream. Keep each bullet under twelve words."; Stream = $true }
    )
    for ($i = 1; $i -le [Math]::Max(0, $RepeatedRequests); $i++) {
        $tests += @{ Name = "D_repeat_$i"; Prompt = "Reply with OK."; Stream = $true }
    }

    foreach ($test in $tests) {
        $result = Invoke-ResponsesRequest $client $apiKey $test.Prompt $test.Stream
        $events = if ($result.Events.Count) { $result.Events -join "," } else { "<none>" }
        $error = if ($result.Error) { $result.Error } else { "<none>" }
        Write-Output "test=$($test.Name) status=$($result.Status) headers_ms=$($result.HeadersMs) total_ms=$($result.TotalMs) terminal=$($result.Terminal) events=$events error=$error"
    }
} finally {
    $client.Dispose()
}
