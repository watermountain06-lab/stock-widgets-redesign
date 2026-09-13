param()
$ErrorActionPreference = 'Stop'
$newsQueries = [ordered]@{NVDA='NVIDIA stock'; AAPL='Apple stock'; GOOGL='Alphabet Google stock'; MSFT='Microsoft stock'; AMZN='Amazon stock'; TSM='TSMC stock'; SPCX='SpaceX'; AVGO='Broadcom stock'; META='Meta stock'; TSLA='Tesla stock'; BRKB='Berkshire Hathaway stock'; MU='Micron stock'}
$newsResult = [ordered]@{}
foreach ($entry in $newsQueries.GetEnumerator()) {
  $query = [uri]::EscapeDataString($entry.Value)
  $response = Invoke-WebRequest "https://news.google.com/rss/search?q=$query&hl=ko&gl=KR&ceid=KR:ko" -TimeoutSec 20
  [xml]$feed = $response.Content
  $articles = @($feed.rss.channel.item | Select-Object -First 3 | ForEach-Object {
    [ordered]@{title=[string]$_.title; url=[string]$_.link; source=[string]$_.source.'#text'; publishedAt=([DateTimeOffset]::Parse([string]$_.pubDate)).ToUniversalTime().ToString('o')}
  })
  $newsResult[$entry.Key] = $articles
}
$payload = [ordered]@{provider='Google News RSS'; updatedAt=[DateTimeOffset]::UtcNow.ToString('o'); stocks=$newsResult} | ConvertTo-Json -Depth 8
$newsOutput = Join-Path $PSScriptRoot 'news-snapshot.json'
[IO.File]::WriteAllText($newsOutput, $payload, [Text.UTF8Encoding]::new($false))
Copy-Item -LiteralPath $newsOutput -Destination (Join-Path $PSScriptRoot 'dist/news-snapshot.json')
Write-Output "Updated news for $($newsResult.Count) stocks."
