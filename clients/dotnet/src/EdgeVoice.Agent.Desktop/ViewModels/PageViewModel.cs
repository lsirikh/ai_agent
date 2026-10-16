using System;
using System.Threading.Tasks;
using Prism.Mvvm;

namespace EdgeVoice.Agent.Desktop.ViewModels;

/// <summary>탭 화면 공통: 상태 메시지와 예외 처리.</summary>
public abstract class PageViewModel : BindableBase
{
    private string _status = "";

    public string Status
    {
        get => _status;
        set => SetProperty(ref _status, value);
    }

    protected async Task RunAsync(Func<Task> action, string? done = null)
    {
        try
        {
            await action();
            if (done is not null)
            {
                Status = done;
            }
        }
        catch (Exception ex)
        {
            Status = "오류: " + ex.Message;
        }
    }
}
