using System.ComponentModel;
using System.Windows;
using EdgeVoice.Agent.Desktop.ViewModels;

namespace EdgeVoice.Agent.Desktop;

public partial class MainWindow : Window
{
    public MainWindow(MainViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
    }

    /// <summary>트레이 상주 앱이므로 창을 닫으면 숨기기만 한다 (종료는 트레이 메뉴).</summary>
    protected override void OnClosing(CancelEventArgs e)
    {
        e.Cancel = true;
        Hide();
    }
}
