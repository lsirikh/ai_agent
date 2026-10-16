using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Layout;
using Avalonia.Platform.Storage;

namespace EdgeVoice.Agent.Desktop;

/// <summary>Avalonia 에는 MessageBox/OpenFileDialog 가 없어 메인 창 기준으로 직접 띄운다.</summary>
public static class Dialogs
{
    private static Window? Owner
        => (Application.Current?.ApplicationLifetime as IClassicDesktopStyleApplicationLifetime)?.Windows.OfType<MainWindow>().FirstOrDefault();

    public static async Task<bool> ConfirmAsync(string title, string message)
    {
        if (Owner is not { } owner)
        {
            return false;
        }

        var dialog = new Window
        {
            Title = title,
            Width = 420,
            SizeToContent = SizeToContent.Height,
            CanResize = false,
            WindowStartupLocation = WindowStartupLocation.CenterOwner,
        };
        var yes = new Button { Content = "예", IsDefault = true, Margin = new Thickness(0, 0, 6, 0) };
        var no = new Button { Content = "아니요", IsCancel = true };
        yes.Click += (_, _) => dialog.Close(true);
        no.Click += (_, _) => dialog.Close(false);
        dialog.Content = new StackPanel
        {
            Margin = new Thickness(16),
            Spacing = 12,
            Children =
            {
                new TextBlock { Text = message, TextWrapping = Avalonia.Media.TextWrapping.Wrap },
                new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Children = { yes, no } },
            },
        };
        return await dialog.ShowDialog<bool>(owner);
    }

    public static async Task<IReadOnlyList<string>> OpenFilesAsync()
    {
        if (Owner is not { } owner)
        {
            return [];
        }

        var files = await owner.StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            AllowMultiple = true,
            FileTypeFilter =
            [
                new FilePickerFileType("문서") { Patterns = ["*.pdf", "*.txt", "*.md", "*.docx"] },
                FilePickerFileTypes.All,
            ],
        });
        return files.Select(f => f.TryGetLocalPath()).OfType<string>().ToList();
    }
}
