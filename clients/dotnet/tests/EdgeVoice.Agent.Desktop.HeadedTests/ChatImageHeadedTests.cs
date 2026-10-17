using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Input.Platform;

namespace EdgeVoice.Agent.Desktop.HeadedTests;

/// <summary>[헤디드] 실제 창: 화면 캡처를 입력창에 Ctrl+V 하면 첨부되고 미리보기가 보인다(전송은 하지 않는다).</summary>
public class ChatImageHeadedTests
{
    private static readonly byte[] Png = Convert.FromBase64String(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==");

    [HeadedFact]
    public Task 클립보드_이미지를_Ctrl_V로_붙이면_첨부된다() => HeadedApp.Run(async () =>
    {
        var (c, w, main) = HeadedApp.Open();
        try
        {
            w.FindControl<TabControl>("Nav")!.SelectedIndex = 1;
            var input = w.FindControl<TextBox>("ChatInput")!;
            var data = new DataObject();
            data.Set("PNG", Png);
            await w.Clipboard!.SetDataObjectAsync(data);

            input.Focus();
            input.RaiseEvent(new KeyEventArgs { RoutedEvent = InputElement.KeyDownEvent, Key = Key.V, KeyModifiers = KeyModifiers.Control });
            await HeadedApp.WaitUntil(() => main.Chat.Attachments.Count == 1);
            await Task.Delay(300);
            HeadedApp.Shot(w, "headed-chat-image-paste");

            Assert.True(main.Chat.HasAttachments);
            Assert.True(main.Chat.SendCommand.CanExecute());
            Assert.True(w.FindControl<ItemsControl>("ChatAttachments")!.IsVisible);
        }
        finally
        {
            main.Chat.Attachments.Clear();
            HeadedApp.Close(c, w, main);
        }
    });
}
