using Avalonia.Controls;
using EdgeVoice.Agent.Desktop.ViewModels;

namespace EdgeVoice.Agent.Desktop;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
    }

    public MainWindow(MainViewModel viewModel)
        : this()
    {
        DataContext = viewModel;
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
}
