using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;
using EdgeVoice.Agent.Desktop.ViewModels;

namespace EdgeVoice.Agent.Desktop;

public partial class MainWindow : Window
{
    /// <summary>클립보드의 이미지 형식(캡처 도구는 PNG, 그 밖은 DIB).</summary>
    private static readonly string[] ClipboardImageFormats = { "PNG", "image/png", "DeviceIndependentBitmap" };

    public MainWindow()
    {
        InitializeComponent();
        var input = this.FindControl<TextBox>("ChatInput");
        input?.AddHandler(KeyDownEvent, OnChatInputKeyDown, RoutingStrategies.Tunnel);
    }

    public MainWindow(MainViewModel viewModel)
        : this()
    {
        DataContext = viewModel;
        viewModel.Chat.ImagePicker = PickImagesAsync;
    }

    /// <summary>트레이 상주 앱이므로 사용자가 창을 닫으면 숨기기만 한다 (종료는 트레이 메뉴).</summary>
    protected override void OnClosing(WindowClosingEventArgs e)
    {
        if (e.CloseReason == WindowCloseReason.WindowClosing)
        {
            e.Cancel = true;
            Hide();
        }

        base.OnClosing(e);
    }

    /// <summary>📎: 이미지 파일을 고른다(여러 장).</summary>
    private async Task<IReadOnlyList<(string Name, byte[] Bytes)>> PickImagesAsync()
    {
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = "채팅에 첨부할 이미지",
            AllowMultiple = true,
            FileTypeFilter = new[] { FilePickerFileTypes.ImageAll },
        });
        var picked = new List<(string, byte[])>();
        foreach (var file in files)
        {
            await using var stream = await file.OpenReadAsync();
            using var memory = new MemoryStream();
            await stream.CopyToAsync(memory);
            picked.Add((file.Name, memory.ToArray()));
        }

        return picked;
    }

    /// <summary>입력창 Ctrl+V: 클립보드에 이미지가 있으면 첨부한다(글자 붙여넣기는 그대로).</summary>
    private async void OnChatInputKeyDown(object? sender, KeyEventArgs e)
    {
        if (e.Key != Key.V || !e.KeyModifiers.HasFlag(KeyModifiers.Control)
            || DataContext is not MainViewModel main || Clipboard is null)
        {
            return;
        }

        var image = await ClipboardImageAsync();
        if (image is not null)
        {
            main.Chat.AttachImage(image, "붙여넣은 이미지");
        }
    }

    private async Task<byte[]?> ClipboardImageAsync()
    {
        var formats = await Clipboard!.GetFormatsAsync();
        foreach (var format in ClipboardImageFormats.Where(formats.Contains))
        {
            if (await Clipboard.GetDataAsync(format) is byte[] bytes && bytes.Length > 0)
            {
                return format == "DeviceIndependentBitmap" ? DibToBmp(bytes) : bytes;
            }
        }

        // 탐색기에서 복사한 이미지 파일
        if (formats.Contains(DataFormats.Files) && await Clipboard.GetDataAsync(DataFormats.Files) is IEnumerable<IStorageItem> items)
        {
            foreach (var file in items.OfType<IStorageFile>())
            {
                await using var stream = await file.OpenReadAsync();
                using var memory = new MemoryStream();
                await stream.CopyToAsync(memory);
                if (ChatViewModel.ImageMime(memory.ToArray()) is not null)
                {
                    return memory.ToArray();
                }
            }
        }

        return null;
    }

    /// <summary>CF_DIB(헤더 없는 비트맵)에 BMP 파일 헤더를 붙인다.</summary>
    public static byte[] DibToBmp(byte[] dib)
    {
        var headerSize = BitConverter.ToInt32(dib, 0);
        var bitCount = BitConverter.ToInt16(dib, 14);
        var compression = BitConverter.ToInt32(dib, 16);
        var colorsUsed = BitConverter.ToInt32(dib, 32);
        var palette = bitCount <= 8 ? (colorsUsed == 0 ? 1 << bitCount : colorsUsed) * 4 : 0;
        var masks = compression == 3 && headerSize == 40 ? 12 : 0; // BI_BITFIELDS
        var offset = 14 + headerSize + palette + masks;

        var bmp = new byte[14 + dib.Length];
        bmp[0] = (byte)'B';
        bmp[1] = (byte)'M';
        BitConverter.GetBytes(bmp.Length).CopyTo(bmp, 2);
        BitConverter.GetBytes(offset).CopyTo(bmp, 10);
        dib.CopyTo(bmp, 14);
        return bmp;
    }
}
