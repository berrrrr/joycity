using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading;
using System.Windows.Forms;
using _003CPrivateImplementationDetails_003E_007BAC6C2DFE_002DD87B_002D4B2C_002D94F2_002D0C219A0FF1EF_007D;
using CefSharp;
using CefSharp.WinForms;
using _00A0;
using _1680;

namespace Joytalk;

internal static class Program
{
	[CompilerGenerated]
	private static class _00A0
	{
		public static EventHandler _00A0;
	}

	[CompilerGenerated]
	private static bool _003CCefAvailable_003Ek__BackingField;

	private static Semaphore _programSemaphore;

	private const int MaxConcurrentInstances = 4;

	private const string SemaphoreName = "JoyTalkSemaphore";

	private static bool _semaphoreAcquired = false;

	private const string UpdateBaseUrl = "https://download.joy-june.com/joytalk/";

	private static readonly string[] UpdateFiles = new string[1] { _3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_2036() };

	[CompilerGenerated]
	private static bool _003CIsWine_003Ek__BackingField;

	[SpecialName]
	[CompilerGenerated]
	public static bool _00A0()
	{
		return _003CCefAvailable_003Ek__BackingField;
	}

	[SpecialName]
	[CompilerGenerated]
	private static void _00A0(bool value)
	{
		_003CCefAvailable_003Ek__BackingField = value;
	}

	[SpecialName]
	private static string _1680()
	{
		return global::_00A0._2000._00A0();
	}

	[DllImport("kernel32.dll")]
	private static extern bool AllocConsole();

	[DllImport("kernel32.dll")]
	private static extern bool FreeConsole();

	[DllImport("kernel32.dll")]
	private static extern bool IsDebuggerPresent();

	[DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
	private static extern bool SetDllDirectory(string lpPathName);

	[DllImport("ntdll.dll")]
	private static extern nint wine_get_version();

	private static bool DetectWine()
	{
		try
		{
			wine_get_version();
			return true;
		}
		catch
		{
			return false;
		}
	}

	[STAThread]
	private static void Main()
	{
		//IL_017f: Unknown result type (might be due to invalid IL or missing references)
		//IL_0127: Unknown result type (might be due to invalid IL or missing references)
		//IL_0131: Expected O, but got Unknown
		//IL_0100: Unknown result type (might be due to invalid IL or missing references)
		Environment.CurrentDirectory = AppDomain.CurrentDomain.BaseDirectory;
		SetDllDirectory(AppDomain.CurrentDomain.BaseDirectory);
		AppDomain.CurrentDomain.ProcessExit += OnProcessExit;
		try
		{
			string baseDirectory = AppDomain.CurrentDomain.BaseDirectory;
			string text = Path.Combine(baseDirectory, _3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_2022());
			var (flag, text2) = CheckNeedsUpdate(baseDirectory, text);
			if (flag)
			{
				try
				{
					File.WriteAllText(text, text2 ?? DateTime.Now.ToString(_3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2002_2022()));
				}
				catch
				{
				}
				if (DownloadAndRunUpdater(baseDirectory))
				{
					return;
				}
			}
			_programSemaphore = new Semaphore(4, 4, _3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_2024());
			_semaphoreAcquired = _programSemaphore.WaitOne(0);
			if (!_semaphoreAcquired)
			{
				DefaultInterpolatedStringHandler defaultInterpolatedStringHandler = new DefaultInterpolatedStringHandler(25, 1);
				defaultInterpolatedStringHandler.AppendLiteral(_3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_2025());
				defaultInterpolatedStringHandler.AppendFormatted(4);
				defaultInterpolatedStringHandler.AppendLiteral(_3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_2027());
				global::_1680._2047._00A0(defaultInterpolatedStringHandler.ToStringAndClear(), _3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_2028());
				return;
			}
			Application.SetHighDpiMode((HighDpiMode)0);
			Application.EnableVisualStyles();
			Application.SetCompatibleTextRenderingDefault(false);
			Application.SetDefaultFont(new Font(_3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._1680_2027(), 9f));
			_1680(DetectWine());
			_00A0(_2000() && TryInitializeCef());
			Application.Run((Form)(object)new global::_00A0._2032());
			if (_00A0())
			{
				ShutdownCef();
			}
		}
		catch (Exception ex)
		{
			global::_1680._2047._00A0(_3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_2029() + ex.Message, _3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_202A());
		}
		finally
		{
			if (_semaphoreAcquired)
			{
				_programSemaphore.Release();
			}
			if (_programSemaphore != null)
			{
				_programSemaphore.Dispose();
			}
		}
	}

	private static (bool needsUpdate, string serverVersion) CheckNeedsUpdate(string baseDir, string updateCachePath)
	{
		try
		{
			string text;
			try
			{
				using HttpClient httpClient = new HttpClient
				{
					Timeout = TimeSpan.FromSeconds(10L)
				};
				HttpResponseMessage result = httpClient.GetAsync(_1680()).Result;
				if (!result.IsSuccessStatusCode)
				{
					return (needsUpdate: false, serverVersion: null);
				}
				using JsonDocument jsonDocument = JsonDocument.Parse(result.Content.ReadAsStringAsync().Result);
				text = _3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_202B();
				if (jsonDocument.RootElement.TryGetProperty(_3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_202C(), out var value))
				{
					text = value.GetString() ?? _3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_202B();
				}
				string[] array = text.Split('.');
				if (array.Length >= 3)
				{
					DefaultInterpolatedStringHandler defaultInterpolatedStringHandler = new DefaultInterpolatedStringHandler(2, 3);
					defaultInterpolatedStringHandler.AppendFormatted(array[0]);
					defaultInterpolatedStringHandler.AppendLiteral(_3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_202D());
					defaultInterpolatedStringHandler.AppendFormatted(array[1]);
					defaultInterpolatedStringHandler.AppendLiteral(_3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_202D());
					defaultInterpolatedStringHandler.AppendFormatted(array[2]);
					text = defaultInterpolatedStringHandler.ToStringAndClear();
				}
			}
			catch
			{
				return (needsUpdate: false, serverVersion: null);
			}
			if (File.Exists(updateCachePath) && string.Equals(File.ReadAllText(updateCachePath).Trim(), text, StringComparison.OrdinalIgnoreCase))
			{
				return (needsUpdate: false, serverVersion: text);
			}
			string text2 = Path.Combine(baseDir, _3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_202E());
			if (!File.Exists(text2))
			{
				return (needsUpdate: true, serverVersion: text);
			}
			string text3 = FileVersionInfo.GetVersionInfo(text2).FileVersion ?? _3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_202B();
			string[] array2 = text3.Split('.');
			if (array2.Length >= 3)
			{
				DefaultInterpolatedStringHandler defaultInterpolatedStringHandler2 = new DefaultInterpolatedStringHandler(2, 3);
				defaultInterpolatedStringHandler2.AppendFormatted(array2[0]);
				defaultInterpolatedStringHandler2.AppendLiteral(_3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_202D());
				defaultInterpolatedStringHandler2.AppendFormatted(array2[1]);
				defaultInterpolatedStringHandler2.AppendLiteral(_3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_202D());
				defaultInterpolatedStringHandler2.AppendFormatted(array2[2]);
				text3 = defaultInterpolatedStringHandler2.ToStringAndClear();
			}
			return (needsUpdate: !string.Equals(text3, text, StringComparison.OrdinalIgnoreCase), serverVersion: text);
		}
		catch
		{
			return (needsUpdate: false, serverVersion: null);
		}
	}

	private static bool DownloadAndRunUpdater(string baseDir)
	{
		//IL_00e6: Unknown result type (might be due to invalid IL or missing references)
		//IL_0171: Unknown result type (might be due to invalid IL or missing references)
		//IL_0144: Unknown result type (might be due to invalid IL or missing references)
		//IL_009b: Unknown result type (might be due to invalid IL or missing references)
		try
		{
			using HttpClient httpClient = new HttpClient
			{
				Timeout = TimeSpan.FromSeconds(30L)
			};
			string[] updateFiles = UpdateFiles;
			foreach (string text in updateFiles)
			{
				string requestUri = _3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_202F() + text;
				string path = Path.Combine(baseDir, text);
				try
				{
					HttpResponseMessage result = httpClient.GetAsync(requestUri).Result;
					if (!result.IsSuccessStatusCode)
					{
						DefaultInterpolatedStringHandler defaultInterpolatedStringHandler = new DefaultInterpolatedStringHandler(22, 2);
						defaultInterpolatedStringHandler.AppendLiteral(_3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_2032());
						defaultInterpolatedStringHandler.AppendFormatted(text);
						defaultInterpolatedStringHandler.AppendLiteral(_3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_2035());
						defaultInterpolatedStringHandler.AppendFormatted(result.StatusCode);
						global::_1680._2047._00A0(defaultInterpolatedStringHandler.ToStringAndClear(), _3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_2033());
						return false;
					}
					byte[] result2 = result.Content.ReadAsByteArrayAsync().Result;
					File.WriteAllBytes(path, result2);
				}
				catch (Exception ex)
				{
					global::_1680._2047._00A0(_3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_2032() + text + _3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._206B() + ex.Message, _3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_2033());
					return false;
				}
			}
			string text2 = Path.Combine(baseDir, _3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_2036());
			if (File.Exists(text2))
			{
				Process.Start(new ProcessStartInfo
				{
					FileName = text2,
					UseShellExecute = true,
					WorkingDirectory = baseDir
				});
				return true;
			}
			global::_1680._2047._00A0(_3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_203E(), _3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_2047());
			return false;
		}
		catch (Exception ex2)
		{
			global::_1680._2047._00A0(_3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_2048() + ex2.Message, _3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_202A());
			return false;
		}
	}

	[SpecialName]
	[CompilerGenerated]
	public static bool _2000()
	{
		return _003CIsWine_003Ek__BackingField;
	}

	[SpecialName]
	[CompilerGenerated]
	private static void _1680(bool value)
	{
		_003CIsWine_003Ek__BackingField = value;
	}

	[MethodImpl(MethodImplOptions.NoInlining)]
	private static bool TryInitializeCef()
	{
		try
		{
			CefSettings cefSettings = new CefSettings();
			if (_2000())
			{
				cefSettings.CefCommandLineArgs.Add(_3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_2049(), _3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2000_2058());
				cefSettings.CefCommandLineArgs.Add(_3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_204A(), _3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2000_2058());
				cefSettings.CefCommandLineArgs.Add(_3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_204B(), _3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2000_2058());
				cefSettings.CefCommandLineArgs.Add(_3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2005_204C(), _3CDA3D22_002DBFAD_002D4812_002DB058_002D4341C38661CE._2000_2058());
			}
			Cef.Initialize(cefSettings);
			return true;
		}
		catch
		{
			return false;
		}
	}

	[MethodImpl(MethodImplOptions.NoInlining)]
	private static void ShutdownCef()
	{
		Cef.Shutdown();
	}

	private static void OnProcessExit(object sender, EventArgs e)
	{
		if (!_semaphoreAcquired || _programSemaphore == null)
		{
			return;
		}
		try
		{
			_programSemaphore.Release();
		}
		catch (SemaphoreFullException)
		{
		}
		finally
		{
			_programSemaphore.Dispose();
		}
	}
}
