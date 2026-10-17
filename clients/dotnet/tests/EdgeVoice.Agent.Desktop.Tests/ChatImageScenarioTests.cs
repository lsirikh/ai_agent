using System.Text.Json.Nodes;
using Avalonia.Headless.XUnit;
using Xunit;

namespace EdgeVoice.Agent.Desktop.Tests;

/// <summary>
/// 채팅 이미지 첨부(멀티모달, 사용자 요청 2026-10-17):
/// 📎·붙여넣기로 첨부 → 전송 요청에 data URL 로 실어 보낸다 →
/// 비전 모델 설명(image_description)을 내 말풍선에 붙여 LLM 이 화면을 어떻게 이해했는지 보여 준다.
/// </summary>
public class ChatImageScenarioTests
{
    private static readonly byte[] Png = Convert.FromBase64String(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==");

    private static void DescribingBackend(FakeBackend b) => b.Sse["/api/chat/message"] = new[]
    {
        ("message", """{"type":"image_description","session_id":"s1","content":"[첨부 이미지 설명]\n엑셀 위에 인증 마법사 창"}"""),
        ("message", """{"type":"token","content":"인증 마법사를 닫아 보세요."}"""),
        ("message", """{"type":"complete"}"""),
    };

    [AvaloniaFact]
    public async Task 첨부한_이미지를_보내고_LLM이_이해한_설명을_내_말풍선에_붙인다()
    {
        using var s = new Scenario(setup: DescribingBackend);
        var chat = s.Main.Chat;

        Assert.True(chat.AttachImage(Png, "capture.png"));
        chat.Input = "엑셀이 왜 안 닫혀?";
        chat.SendCommand.Execute();
        await Scenario.WaitUntil(() => !chat.IsBusy && chat.Messages.Count >= 2);

        var body = JsonNode.Parse(s.Backend.Requests.Last(r => r.Request == "POST /api/chat/message").Body)!;
        Assert.StartsWith("data:image/png;base64,", body["images"]![0]!.ToString());
        var user = chat.Messages[^2];
        Assert.Contains("엑셀이 왜 안 닫혀?", user.Text);
        Assert.Contains("인증 마법사 창", user.Text);
        Assert.Equal("인증 마법사를 닫아 보세요.", chat.Messages[^1].Text);
        Assert.Empty(chat.Attachments);
    }

    [AvaloniaFact]
    public async Task 글_없이_이미지만_보내도_된다()
    {
        using var s = new Scenario(setup: DescribingBackend);
        var chat = s.Main.Chat;

        chat.AttachImage(Png, "capture.png");

        Assert.True(chat.SendCommand.CanExecute());
        chat.SendCommand.Execute();
        await Scenario.WaitUntil(() => !chat.IsBusy && chat.Messages.Count >= 2);
        var body = JsonNode.Parse(s.Backend.Requests.Last(r => r.Request == "POST /api/chat/message").Body)!;
        Assert.False(string.IsNullOrWhiteSpace(body["message"]!.ToString()));
    }

    [AvaloniaFact]
    public void 이미지가_아니거나_세_장째면_첨부하지_않는다()
    {
        using var s = new Scenario();
        var chat = s.Main.Chat;

        Assert.False(chat.AttachImage(new byte[] { 1, 2, 3, 4 }, "note.txt"));
        Assert.True(chat.AttachImage(Png, "a.png"));
        Assert.True(chat.AttachImage(Png, "b.png"));
        Assert.False(chat.AttachImage(Png, "c.png"));

        Assert.Equal(2, chat.Attachments.Count);
        chat.RemoveAttachmentCommand.Execute(chat.Attachments[0]);
        Assert.Single(chat.Attachments);
    }
}

public class ClipboardImageTests
{
    [Fact]
    public void DIB_클립보드_이미지에_BMP_헤더를_붙이면_이미지로_읽힌다()
    {
        // 1x1 32비트 BITMAPINFOHEADER + 픽셀 하나 (Win+Shift+S 가 아닌 프로그램은 DIB 만 올린다)
        var dib = new byte[40 + 4];
        BitConverter.GetBytes(40).CopyTo(dib, 0);
        BitConverter.GetBytes(1).CopyTo(dib, 4);
        BitConverter.GetBytes(1).CopyTo(dib, 8);
        BitConverter.GetBytes((short)1).CopyTo(dib, 12);
        BitConverter.GetBytes((short)32).CopyTo(dib, 14);

        var bmp = MainWindow.DibToBmp(dib);

        Assert.Equal("image/bmp", EdgeVoice.Agent.Desktop.ViewModels.ChatViewModel.ImageMime(bmp));
        Assert.Equal(54, BitConverter.ToInt32(bmp, 10)); // 픽셀 시작 = 14 + 40
    }
}

public class ChatImageDropTests
{
    private static readonly byte[] Png = Convert.FromBase64String(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==");

    [Avalonia.Headless.XUnit.AvaloniaFact]
    public void 끌어다_놓은_파일_중_이미지만_첨부한다()
    {
        // 사용자 요청: 채팅창에 사진을 끌어다 놓아도 분석되게(📎·Ctrl+V 와 같은 첨부)
        using var s = new Scenario();
        var chat = s.Main.Chat;

        var attached = chat.AttachFiles(new[] { ("메모.txt", new byte[] { 1, 2, 3 }), ("화면.png", Png) });

        Assert.Equal(1, attached);
        Assert.Single(chat.Attachments);
        Assert.Equal("화면.png", chat.Attachments[0].Name);
    }
}
