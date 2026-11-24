// AnimeStudio.CLI 안에서 여러 게임 파일을 한꺼번에 읽어 모델 + 동작을 FBX 하나로 내보내는 시작 훅 (zzz-game-extract 스킬, 2026-11-24)
// CLI는 파일을 하나씩 따로 읽어서, 몸 메시·동작이 다른 파일에 있으면 같이 안 나온다. 그래서 CLI 자체 코드(Studio, Exporter)를
// 반사(reflection)로 불러 한 번에 읽게 한다. CLI 코드는 그대로 쓰고 고치지 않는다.
// 빌드: C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe -target:library -out:ExtractHook.dll ExtractHook.cs
// 실행 (app 폴더에서):
//   set DOTNET_ROOT=<휴대용 .NET 10>
//   set DOTNET_STARTUP_HOOKS=<이 dll 전체 경로>
//   set ZX_LIST=<읽을 .blk 경로 목록 txt (한 줄에 하나)>
//   set ZX_OUT=<출력 폴더, 없어야 함>
//   set ZX_MODEL=<내보낼 Animator 이름 정규식>
//   set ZX_CLIPS=<같이 넣을 AnimationClip 이름 정규식>
//   set ZX_DRY=1  (선택: 내보내지 않고 찾은 항목만 출력)
//   AnimeStudio.CLI.exe x x --game ZZZ      (인자는 형식만 맞추면 됨, 훅이 먼저 끝내고 종료한다)
// 게임 파일은 읽기만 한다. 출력은 ZX_OUT 안에만 쓴다.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.RegularExpressions;

internal class StartupHook {
    static Assembly Find(string name) {
        foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
            if (a.GetName().Name == name) return a;
        return Assembly.Load(new AssemblyName(name));
    }

    static Type T(Assembly a, string full) {
        var t = a.GetType(full);
        if (t == null) throw new Exception("형식을 못 찾음: " + full);
        return t;
    }

    public static void Initialize() {
        string list = Environment.GetEnvironmentVariable("ZX_LIST");
        if (string.IsNullOrEmpty(list)) return;   // 변수가 없으면 원래 CLI 그대로
        int code = 0;
        try { Run(list); }
        catch (Exception ex) {
            for (Exception e = ex; e != null; e = e.InnerException)
                Console.WriteLine("[훅 오류] " + e.GetType().FullName + ": " + e.Message + "\n" + e.StackTrace);
            code = 1;
        }
        Console.Out.Flush();
        Environment.Exit(code);
    }

    static string Need(string key) {
        string v = Environment.GetEnvironmentVariable(key);
        if (string.IsNullOrEmpty(v)) throw new Exception("환경 변수가 비어 있음: " + key);
        return v;
    }

    static void Run(string list) {
        bool dry = Environment.GetEnvironmentVariable("ZX_DRY") == "1";
        string outDir = dry ? Environment.GetEnvironmentVariable("ZX_OUT") : Need("ZX_OUT");
        var modelRx = new Regex(Need("ZX_MODEL"));
        var clipRx = new Regex(Need("ZX_CLIPS"));
        if (!dry && Directory.Exists(outDir) && Directory.EnumerateFileSystemEntries(outDir).Any())
            throw new Exception("출력 폴더가 비어 있지 않아 덮어쓰지 않습니다: " + outDir);

        var files = File.ReadAllLines(list).Select(s => s.Trim()).Where(s => s.Length > 0).ToArray();
        foreach (var f in files) if (!File.Exists(f)) throw new Exception("파일 없음: " + f);

        var core = Find("AnimeStudio");
        var cli = Find("AnimeStudio.CLI");
        var studio = T(cli, "AnimeStudio.CLI.Studio");
        var exporter = T(cli, "AnimeStudio.CLI.Exporter");
        var itemT = T(cli, "AnimeStudio.CLI.AssetItem");
        var gm = T(core, "AnimeStudio.GameManager");
        var classId = T(core, "AnimeStudio.ClassIDType");

        // 로그를 콘솔로
        var loggerT = T(core, "AnimeStudio.Logger");
        var consoleLoggerT = cli.GetTypes().FirstOrDefault(t => t.Name == "ConsoleLogger");
        if (consoleLoggerT != null) {
            var fDef = loggerT.GetField("Default", BindingFlags.Public | BindingFlags.Static);
            var pDef = loggerT.GetProperty("Default", BindingFlags.Public | BindingFlags.Static);
            var inst = Activator.CreateInstance(consoleLoggerT, true);
            if (fDef != null) fDef.SetValue(null, inst); else if (pDef != null) pDef.SetValue(null, inst, null);
        }

        var game = gm.GetMethod("GetGame", new[] { typeof(string) }).Invoke(null, new object[] { "ZZZ" });
        if (game == null) throw new Exception("ZZZ 게임 설정을 못 찾음");
        studio.GetField("Game", BindingFlags.Public | BindingFlags.Static).SetValue(null, game);
        var am = studio.GetField("assetsManager", BindingFlags.Public | BindingFlags.Static).GetValue(null);
        SetMember(am, "Game", game);

        Console.WriteLine("[훅] 파일 " + files.Length + "개를 한꺼번에 읽습니다");
        var load = am.GetType().GetMethods().First(m => m.Name == "LoadFiles" && m.GetParameters().Length == 1 && m.GetParameters()[0].ParameterType == typeof(string[]));
        load.Invoke(am, new object[] { files });

        // CLI의 BuildAssetData로 내보낼 항목 목록을 만든다 (이름 필터: 모델 또는 동작)
        var build = studio.GetMethod("BuildAssetData", BindingFlags.Public | BindingFlags.Static);
        var noTypes = Array.CreateInstance(classId, 0);
        var names = new Regex[] { modelRx, clipRx };
        var args = new object[] { noTypes, names, new Regex[0], 0 };
        build.Invoke(null, args);
        var exportable = (IList)studio.GetField("exportableAssets", BindingFlags.Public | BindingFlags.Static).GetValue(null);

        var fText = itemT.GetField("Text"); var fType = itemT.GetField("Type");
        object animator = null;
        var clips = (IList)Activator.CreateInstance(typeof(List<>).MakeGenericType(itemT));
        var seen = new HashSet<string>();
        foreach (var it in exportable) {
            string text = (string)fText.GetValue(it); string type = fType.GetValue(it).ToString();
            if (type == "Animator" && modelRx.IsMatch(text)) {
                if (animator == null) animator = it;
                Console.WriteLine("[훅] 모델: " + text);
            } else if (type == "AnimationClip" && clipRx.IsMatch(text) && seen.Add(text)) {
                clips.Add(it);
            }
        }
        Console.WriteLine("[훅] 동작 " + clips.Count + "개");
        foreach (var it in clips) Console.WriteLine("    " + fText.GetValue(it));
        if (animator == null) throw new Exception("모델(Animator)을 못 찾음");
        if (dry) { Console.WriteLine("[훅] 확인만 하고 끝냄 (ZX_DRY=1)"); return; }

        Directory.CreateDirectory(outDir);
        var exp = exporter.GetMethod("ExportAnimator", BindingFlags.Public | BindingFlags.Static);
        var ok = exp.Invoke(null, new object[] { animator, outDir, clips });
        Console.WriteLine("[훅] 내보내기 결과: " + ok);
    }

    static void SetMember(object o, string name, object v) {
        var f = o.GetType().GetField(name, BindingFlags.Public | BindingFlags.Instance);
        if (f != null) { f.SetValue(o, v); return; }
        var p = o.GetType().GetProperty(name, BindingFlags.Public | BindingFlags.Instance);
        if (p != null) { p.SetValue(o, v, null); return; }
        throw new Exception("멤버 없음: " + name);
    }
}
