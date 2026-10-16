using System.Diagnostics;
using System.Net.Http.Json;
using System.Text.Json.Nodes;
using Avalonia.Controls;

namespace EdgeVoice.Agent.Desktop.HeadedTests;

/// <summary>
/// [헤디드] 음성·채팅 통합 대화. 실제 백엔드 + 오케스트레이터 + vLLM 이 떠 있어야 한다.
/// 음성 턴은 마이크 대신 Redis(docker exec ev-redis redis-cli)로 웨이크워드·STT 결과를 주입한다.
/// </summary>
public class UnifiedConversationHeadedTests
{
    private static readonly HttpClient Http = new() { BaseAddress = new Uri(HeadedApp.BackendUrl.TrimEnd('/') + "/") };

    /// <summary>"Hey Jarvis" → STT 결과를 Redis 로 흘려 오케스트레이터가 음성 턴을 돌게 한다.</summary>
    private static async Task InjectVoiceTurn(string text)
    {
        Publish("edgevoice:wake_word:detected", "{}");
        await Task.Delay(1000);
        Publish("edgevoice:stt:result", new JsonObject { ["text"] = text }.ToJsonString());
    }

    private static void Publish(string channel, string json)
    {
        var psi = new ProcessStartInfo("docker") { RedirectStandardOutput = true, RedirectStandardError = true };
        foreach (var arg in new[] { "exec", "ev-redis", "redis-cli", "PUBLISH", channel, json })
        {
            psi.ArgumentList.Add(arg);
        }

        using var p = Process.Start(psi)!;
        p.WaitForExit(10_000);
        Assert.Equal(0, p.ExitCode);
    }

    private static async Task<JsonArray> SessionMessages(string sessionId) =>
        (await Http.GetFromJsonAsync<JsonObject>($"api/sessions/{sessionId}/messages"))!["messages"]!.AsArray();

    [HeadedFact]
    public Task 채팅_화면을_연_채_음성_턴을_주입하면_새로고침_없이_음성_말풍선_2개가_붙는다() => HeadedApp.Run(async () =>
    {
        var (c, w, main) = HeadedApp.Open();
        try
        {
            var chat = main.Chat;
            w.FindControl<TabControl>("Nav")!.SelectedIndex = 1;
            await HeadedApp.WaitUntil(() => chat.SessionId is not null);
            await Task.Delay(1000);
            var before = chat.Messages.Count;

            await InjectVoiceTurn("헤디드 음성 시험이야. 한 문장으로 답해 줘.");

            await HeadedApp.WaitUntil(() => chat.Messages.Count >= before + 2, 120_000);
            HeadedApp.Shot(w, "headed-voice-turn");
            var turn = chat.Messages.Skip(before).Take(2).ToArray();
            Assert.All(turn, m => Assert.True(m.IsVoice));
            Assert.Equal(("User", "AI"), (turn[0].Role, turn[1].Role));
            Assert.Contains("헤디드 음성 시험", turn[0].Text);
            Assert.False(string.IsNullOrWhiteSpace(turn[1].Text));
        }
        finally
        {
            HeadedApp.Close(c, w, main);
        }
    });

    [HeadedFact]
    public Task 앱을_닫았다_열면_지난_세션_히스토리가_보이고_텍스트_후속_질문이_이어진다() => HeadedApp.Run(async () =>
    {
        string? sessionId;
        var (c, w, main) = HeadedApp.Open();
        try
        {
            var chat = main.Chat;
            await HeadedApp.WaitUntil(() => chat.SessionId is not null);
            await Task.Delay(1000);
            var before = chat.Messages.Count;
            chat.UseRag = false;
            chat.Input = "내 별명은 파란고래야. 기억해 줘.";
            chat.SendCommand.Execute();
            await HeadedApp.WaitUntil(() => !chat.IsBusy && chat.Messages.Count == before + 2, 120_000);
            sessionId = chat.SessionId;
        }
        finally
        {
            HeadedApp.Close(c, w, main);
        }

        (c, w, main) = HeadedApp.Open();
        try
        {
            var chat = main.Chat;
            w.FindControl<TabControl>("Nav")!.SelectedIndex = 1;
            await HeadedApp.WaitUntil(() => chat.Messages.Any(m => m.Text.Contains("파란고래")));
            Assert.Equal(sessionId, chat.SessionId);

            var before = chat.Messages.Count;
            chat.UseRag = false;
            chat.Input = "내 별명이 뭐라고 했지? 별명만 말해 줘.";
            chat.SendCommand.Execute();
            await HeadedApp.WaitUntil(() => !chat.IsBusy && chat.Messages.Count == before + 2, 120_000);
            HeadedApp.Shot(w, "headed-reopen-followup");

            Assert.Contains("파란고래", chat.Messages[^1].Text);
        }
        finally
        {
            HeadedApp.Close(c, w, main);
        }
    });

    [HeadedFact]
    public Task 새_대화를_누르면_목록이_비고_이전_세션은_History_에_남고_다음_음성_턴은_새_세션에_들어간다() => HeadedApp.Run(async () =>
    {
        var (c, w, main) = HeadedApp.Open();
        try
        {
            var chat = main.Chat;
            w.FindControl<TabControl>("Nav")!.SelectedIndex = 1;
            await HeadedApp.WaitUntil(() => chat.SessionId is not null);
            var old = chat.SessionId!;
            chat.UseRag = false;
            chat.Input = "이전 세션에 남길 말";
            chat.SendCommand.Execute();
            await HeadedApp.WaitUntil(() => !chat.IsBusy, 120_000);

            w.FindControl<Button>("NewConversation")!.Command!.Execute(null);
            await HeadedApp.WaitUntil(() => chat.SessionId != old && chat.Messages.Count == 0);
            HeadedApp.Shot(w, "headed-new-conversation");

            main.History.RefreshCommand.Execute();
            await HeadedApp.WaitUntil(() => main.History.Items.Any(i => i.Query.Contains("이전 세션에 남길 말")));

            await InjectVoiceTurn("새 세션 음성 시험이야. 짧게 답해 줘.");
            var fresh = chat.SessionId!;
            await HeadedApp.WaitUntil(() => chat.Messages.Count >= 2, 120_000);
            var messages = await SessionMessages(fresh);
            Assert.Contains(messages, m => m!["source"]!.ToString() == "voice" && m["content"]!.ToString().Contains("새 세션 음성"));
            Assert.DoesNotContain(await SessionMessages(old), m => m!["content"]!.ToString().Contains("새 세션 음성"));
        }
        finally
        {
            HeadedApp.Close(c, w, main);
        }
    });

    [HeadedFact]
    public Task History_페이지가_실제_백엔드_메시지를_질문_응답으로_보여준다() => HeadedApp.Run(async () =>
    {
        var (c, w, main) = HeadedApp.Open();
        try
        {
            var chat = main.Chat;
            await HeadedApp.WaitUntil(() => chat.SessionId is not null);
            chat.UseRag = false;
            chat.Input = "히스토리 확인용 질문";
            chat.SendCommand.Execute();
            await HeadedApp.WaitUntil(() => !chat.IsBusy, 120_000);

            w.FindControl<TabControl>("Nav")!.SelectedIndex = 4;
            main.History.RefreshCommand.Execute();
            await HeadedApp.WaitUntil(() => main.History.Items.Any(i => i.Query == "히스토리 확인용 질문"));
            HeadedApp.Shot(w, "headed-history");

            var item = main.History.Items.First(i => i.Query == "히스토리 확인용 질문");
            Assert.False(string.IsNullOrWhiteSpace(item.Response));
            Assert.EndsWith("건", main.History.Status);
        }
        finally
        {
            HeadedApp.Close(c, w, main);
        }
    });
}
