using System.Net.Http.Json;
using System.Runtime.CompilerServices;
using System.Text.Json.Nodes;

namespace EdgeVoice.Agent.Core;

/// <summary>SSE(text/event-stream) 이벤트 하나.</summary>
public sealed record ServerEvent(string Type, string Data)
{
    public JsonNode? Json => JsonNode.Parse(Data);
}

/// <summary>
/// EdgeVoice 백엔드 REST/SSE 클라이언트.
/// 응답 형태가 서비스마다 달라 DTO 대신 JsonNode 로 다룬다.
/// </summary>
public sealed class EdgeVoiceApiClient
{
    private readonly HttpClient _http;

    public EdgeVoiceApiClient(EdgeVoiceOptions options)
    {
        _http = new HttpClient
        {
            BaseAddress = new Uri(options.BackendUrl.TrimEnd('/') + "/"),
            Timeout = Timeout.InfiniteTimeSpan,
        };
    }

    public Task<JsonNode?> GetAsync(string path, CancellationToken ct = default)
        => SendAsync(HttpMethod.Get, path, null, ct);

    public async Task<JsonNode?> SendAsync(HttpMethod method, string path, object? body, CancellationToken ct = default)
    {
        using var req = new HttpRequestMessage(method, path.TrimStart('/'));
        if (body is not null)
        {
            req.Content = JsonContent.Create(body);
        }

        using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        cts.CancelAfter(TimeSpan.FromSeconds(30));
        using var res = await _http.SendAsync(req, cts.Token).ConfigureAwait(false);
        var text = await res.Content.ReadAsStringAsync(cts.Token).ConfigureAwait(false);
        if (!res.IsSuccessStatusCode)
        {
            throw new HttpRequestException($"{(int)res.StatusCode} {method} /{path.TrimStart('/')}: {text}");
        }

        return string.IsNullOrWhiteSpace(text) ? null : JsonNode.Parse(text);
    }

    public async Task<JsonNode?> UploadAsync(string path, string filePath, CancellationToken ct = default)
    {
        await using var file = File.OpenRead(filePath);
        using var form = new MultipartFormDataContent
        {
            { new StreamContent(file), "file", Path.GetFileName(filePath) },
        };
        using var res = await _http.PostAsync(path.TrimStart('/'), form, ct).ConfigureAwait(false);
        var text = await res.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
        if (!res.IsSuccessStatusCode)
        {
            throw new HttpRequestException($"{(int)res.StatusCode} 업로드 실패: {text}");
        }

        return string.IsNullOrWhiteSpace(text) ? null : JsonNode.Parse(text);
    }

    /// <summary>GET SSE 스트림 구독 (/api/dashboard/stream, /api/logs/stream 등).</summary>
    public IAsyncEnumerable<ServerEvent> StreamAsync(string path, CancellationToken ct = default)
        => StreamAsync(new HttpRequestMessage(HttpMethod.Get, path.TrimStart('/')), ct);

    /// <summary>POST /api/chat/message — 응답 토큰을 SSE 로 스트리밍한다.</summary>
    public IAsyncEnumerable<ServerEvent> ChatAsync(string message, string? sessionId, bool useRag, CancellationToken ct = default)
    {
        var req = new HttpRequestMessage(HttpMethod.Post, "api/chat/message")
        {
            Content = JsonContent.Create(new { message, session_id = sessionId, use_rag = useRag }),
        };
        return StreamAsync(req, ct);
    }

    private async IAsyncEnumerable<ServerEvent> StreamAsync(HttpRequestMessage req, [EnumeratorCancellation] CancellationToken ct)
    {
        using (req)
        using (var res = await _http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, ct).ConfigureAwait(false))
        {
            res.EnsureSuccessStatusCode();
            using var reader = new StreamReader(await res.Content.ReadAsStreamAsync(ct).ConfigureAwait(false));

            var type = "message";
            var data = new List<string>();
            while (await reader.ReadLineAsync(ct).ConfigureAwait(false) is { } line)
            {
                if (line.Length == 0)
                {
                    if (data.Count > 0)
                    {
                        yield return new ServerEvent(type, string.Join("\n", data));
                    }

                    type = "message";
                    data.Clear();
                }
                else if (line.StartsWith("event:", StringComparison.Ordinal))
                {
                    type = line[6..].Trim();
                }
                else if (line.StartsWith("data:", StringComparison.Ordinal))
                {
                    data.Add(line[5..].TrimStart());
                }
            }

            if (data.Count > 0)
            {
                yield return new ServerEvent(type, string.Join("\n", data));
            }
        }
    }
}
