# Pravi precicu "Asistent KATASTAR" na radnoj povrsini i u Start meniju (pokrece program bez crnog prozora).
# Precica dobija isti Windows ID aplikacije kao program, pa taskbar koristi ostru ikonicu sa precice
# i zakacena ikonica se ne duplira kad se program otvori.
$appId = "advokatcolja.asistentkatastar"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyw = $null
try {
    $py = (& py -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1).Trim()
    if ($py) { $pyw = Join-Path (Split-Path $py) "pythonw.exe" }
} catch { }
if (-not $pyw -or -not (Test-Path $pyw)) {
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($cmd) { $pyw = $cmd.Source }
}
if ($env:AK_PYTHONW -and (Test-Path $env:AK_PYTHONW)) { $pyw = $env:AK_PYTHONW }
if (-not $pyw -or -not (Test-Path $pyw)) {
    Write-Host "Nije pronadjen pythonw.exe. Instaliraj Python (python.org) sa opcijom 'py launcher'." -ForegroundColor Red
    exit 1
}
$ikona = Join-Path $dir "asistent_katastar.ico"
if (-not (Test-Path $ikona)) { $ikona = Join-Path $dir "katastar.ico" }

$kod = @'
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
namespace AsistentKatastar {
    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IPropertyStore {
        [PreserveSig] int GetCount(out uint c);
        [PreserveSig] int GetAt(uint i, out PropertyKey k);
        [PreserveSig] int GetValue(ref PropertyKey k, IntPtr v);
        [PreserveSig] int SetValue(ref PropertyKey k, IntPtr v);
        [PreserveSig] int Commit();
    }
    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    public struct PropertyKey { public Guid fmtid; public uint pid; }
    public static class Precica {
        public static void PostaviId(string putanja, string id) {
            Type t = Type.GetTypeFromCLSID(new Guid("00021401-0000-0000-C000-000000000046"));
            object link = Activator.CreateInstance(t);
            try {
                IPersistFile pf = (IPersistFile)link;
                pf.Load(putanja, 2);
                IPropertyStore ps = (IPropertyStore)link;
                PropertyKey k = new PropertyKey();
                k.fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");
                k.pid = 5;
                // PROPVARIANT VT_LPWSTR (31): 8 bajtova zaglavlja + pokazivac na tekst
                IntPtr pv = Marshal.AllocCoTaskMem(24);
                IntPtr tekst = Marshal.StringToCoTaskMemUni(id);
                try {
                    for (int i = 0; i < 24; i++) Marshal.WriteByte(pv, i, 0);
                    Marshal.WriteInt16(pv, 0, 31);
                    Marshal.WriteIntPtr(pv, 8, tekst);
                    int hr = ps.SetValue(ref k, pv);
                    if (hr != 0) Marshal.ThrowExceptionForHR(hr);
                    hr = ps.Commit();
                    if (hr != 0) Marshal.ThrowExceptionForHR(hr);
                } finally {
                    Marshal.FreeCoTaskMem(tekst);
                    Marshal.FreeCoTaskMem(pv);
                }
                pf.Save(putanja, true);
            } finally {
                Marshal.ReleaseComObject(link);
            }
        }
    }
}
'@
$imaId = $true
try { Add-Type -TypeDefinition $kod -ErrorAction Stop } catch { $imaId = $false }

$ws = New-Object -ComObject WScript.Shell
foreach ($mapa in @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs"))) {
    $putanja = Join-Path $mapa "Asistent KATASTAR.lnk"
    $lnk = $ws.CreateShortcut($putanja)
    $lnk.TargetPath = $pyw
    $lnk.Arguments = '"' + (Join-Path $dir "asistent_katastar.py") + '"'
    $lnk.WorkingDirectory = $dir
    $lnk.IconLocation = $ikona + ",0"
    $lnk.Description = "Asistent KATASTAR - pretraga i pracenje parcela"
    $lnk.Save()
    if ($imaId) {
        try { [AsistentKatastar.Precica]::PostaviId($putanja, $appId) }
        catch { $imaId = $false; Write-Host "Napomena: ID aplikacije nije upisan u precicu ($($_.Exception.Message))." -ForegroundColor Yellow }
    }
    Write-Host "Napravljena precica: $putanja"
}
if (-not $imaId) {
    Write-Host "Precica radi, ali taskbar mozda nece spojiti zakacenu ikonicu i otvoren program." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Gotovo. Desni klik na precicu Asistent KATASTAR > Zakaci na traku zadataka (Windows 11: Prikazi vise opcija)."
