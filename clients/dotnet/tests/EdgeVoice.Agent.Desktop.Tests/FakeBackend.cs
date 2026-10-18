using System.Collections.Concurrent;
using System.Net;
using System.Net.Sockets;
using System.Text;

namespace EdgeVoice.Agent.Desktop.Tests;

/// <summary>
/// 시나리오 테스트용 가짜 EdgeVoice 백엔드(HttpListener). 경로별 JSON / SSE 응답을 돌려주고 받은 요청을 기록한다.
/// </summary>
public sealed class FakeBackend : IDisposable
{
    private readonly HttpListener _listener = new();

    public FakeBackend()
    {
        var probe = new TcpListener(IPAddress.Loopback, 0);
        probe.Start();
        var port = ((IPEndPoint)probe.LocalEndpoint).Port;
        probe.Stop();

        Url = $"http://127.0.0.1:{port}/";
        _listener.Prefixes.Add(Url);
        _listener.Start();
        _ = Task.Run(LoopAsync);
    }

    public string Url { get; }

    /// <summary>경로(쿼리 제외) → JSON 응답 본문.</summary>
    public ConcurrentDictionary<string, string> Json { get; } = new()
    {
        ["/api/dashboard/init"] = """
            {"services":{"orchestrator":{"status":"healthy","state":"IDLE"},"stt":{"status":"healthy"},"tts":{"status":"unhealthy"}},
             "system":{"gpu":{"available":true,"used_gb":6.5,"total_gb":16,"utilization_percent":42},
                       "sessions":{"active":3},"documents":{"count":7}}}
            """,
        ["/api/logs/stats"] = """{"total":12,"by_level":{"INFO":8,"WARNING":3,"ERROR":1},"by_service":{"stt":5,"llm":7}}""",
        ["/api/logs"] = """{"logs":[{"created_at":"2026-10-16T10:00:00","level":"INFO","service":"stt","stage":"transcribe","message":"ok","duration_ms":120}]}""",
        ["/api/history"] = """
            {"messages":[{"id":"m2","session_id":"s1","role":"assistant","content":"반가워요","timestamp":"2026-10-16T10:00:05","source":"web"},
                         {"id":"m1","session_id":"s1","role":"user","content":"안녕","timestamp":"2026-10-16T10:00:00","source":"web"}],"total":2}
            """,
        ["/api/knowledge/documents"] = """{"documents":[{"id":"d1","filename":"manual.pdf","chunk_count":12,"uploaded_at":"2026-10-01"}]}""",
        ["/api/settings/options"] = """
            {"tts_engines":[{"id":"melo","display_name":"MeloTTS","recommended_for":"ko"}],
             "stt_models":[{"id":"small","display_name":"Whisper Small","vram_gb":1,"korean_quality":"good"}],
             "llm_models":[{"id":"qwen","display_name":"Qwen","vram_gb":8}],
             "current":{"tts_engine":"melo","tts_voice":"KR","stt_model":"small","llm_model":"qwen"}}
            """,
        ["/api/settings/general"] = """{"wake_word":"alexa","language":"en","voice_speed":1.5,"wake_word_threshold":0.6,"end_pause_seconds":2,"listening_timeout_seconds":20}""",
        ["/api/settings/llm/context"] = """{"context_enabled":false,"context_window_size":10}""",
        ["/api/settings/mcp"] = """{"servers":[]}""",
        ["/api/settings/skills"] = """{"builtin":[],"disabled_tools":[],"prompts":[]}""",
    };

    /// <summary>경로 → HTTP 상태 코드 (없으면 200). 실패 응답 시나리오용.</summary>
    public ConcurrentDictionary<string, int> StatusCodes { get; } = new();

    /// <summary>경로 → SSE 이벤트 목록 (event, data).</summary>
    public ConcurrentDictionary<string, (string Event, string Data)[]> Sse { get; } = new()
    {
        ["/api/chat/message"] = new[]
        {
            ("message", """{"type":"rag_context","session_id":"s1","sources":[{"filename":"manual.pdf"}]}"""),
            ("message", """{"type":"token","content":"안녕"}"""),
            ("message", """{"type":"token","content":"하세요"}"""),
            ("message", """{"type":"complete"}"""),
        },
        ["/api/logs/stream"] = Array.Empty<(string, string)>(),
        ["/api/status/stream"] = Array.Empty<(string, string)>(),
    };

    /// <summary>받은 요청 "METHOD /path" → 본문.</summary>
    public ConcurrentQueue<(string Request, string Body)> Requests { get; } = new();

    /// <summary>받은 요청의 경로+쿼리 (필터 쿼리 확인용).</summary>
    public ConcurrentQueue<string> Queries { get; } = new();

    private async Task LoopAsync()
    {
        while (_listener.IsListening)
        {
            HttpListenerContext ctx;
            try
            {
                ctx = await _listener.GetContextAsync();
            }
            catch (Exception)
            {
                return;
            }

            _ = Task.Run(() => Handle(ctx));
        }
    }

    private void Handle(HttpListenerContext ctx)
    {
        using var reader = new StreamReader(ctx.Request.InputStream);
        var path = ctx.Request.Url!.AbsolutePath;
        Requests.Enqueue(($"{ctx.Request.HttpMethod} {path}", reader.ReadToEnd()));
        Queries.Enqueue(ctx.Request.Url.PathAndQuery);

        string body;
        if (Sse.TryGetValue(path, out var events))
        {
            ctx.Response.ContentType = "text/event-stream";
            body = string.Concat(events.Select(e => $"event: {e.Event}\ndata: {e.Data}\n\n"));
        }
        else if (Json.TryGetValue(path, out var json))
        {
            ctx.Response.ContentType = "application/json";
            ctx.Response.StatusCode = StatusCodes.GetValueOrDefault(path, 200);
            body = json;
        }
        else if (ctx.Request.HttpMethod != "GET")
        {
            ctx.Response.ContentType = "application/json";
            body = """{"status":"ok","wake_word":"alexa","restart_required":[]}""";
        }
        else
        {
            ctx.Response.StatusCode = 404;
            body = "{}";
        }

        var bytes = Encoding.UTF8.GetBytes(body);
        try
        {
            ctx.Response.OutputStream.Write(bytes);
            ctx.Response.Close();
        }
        catch (Exception)
        {
            // 클라이언트가 먼저 끊은 경우
        }
    }

    public void Dispose()
    {
        if (_listener.IsListening)
        {
            _listener.Close();
        }
    }
}
