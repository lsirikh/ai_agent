namespace EdgeVoice.Agent.Core;

/// <summary>이 PC 의 시간대를 서버(Python zoneinfo)가 아는 IANA 이름으로.</summary>
public static class PcTimeZone
{
    public static string IanaId()
    {
        var local = TimeZoneInfo.Local;
        if (local.HasIanaId)
        {
            return local.Id;
        }

        return TimeZoneInfo.TryConvertWindowsIdToIanaId(local.Id, out var iana) ? iana : "Asia/Seoul";
    }

    /// <summary>화면 표시용 PC 지금 시각.</summary>
    public static string NowText() => DateTime.Now.ToString("yyyy년 MM월 dd일 HH시 mm분");
}
