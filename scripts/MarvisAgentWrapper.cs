using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;

public static class MarvisAgentWrapper
{
    private const string BackupExeName = "MarvisAgent.real.exe";
    private const int DefaultLocalLlmPort = 19080;

    public static int Main(string[] args)
    {
        string wrapperPath = Process.GetCurrentProcess().MainModule.FileName;
        string agentDir = Path.GetDirectoryName(wrapperPath);
        string realExe = Environment.GetEnvironmentVariable("MARVIS_AGENT_WRAPPER_REAL_EXE");
        if (String.IsNullOrWhiteSpace(realExe))
        {
            realExe = Path.Combine(agentDir, BackupExeName);
        }

        string localPortText = Environment.GetEnvironmentVariable("MARVIS_AGENT_WRAPPER_LOCAL_LLM_PORT");
        int localPort = DefaultLocalLlmPort;
        if (!String.IsNullOrWhiteSpace(localPortText))
        {
            Int32.TryParse(localPortText, out localPort);
        }
        if (localPort <= 0 || localPort > 65535)
        {
            localPort = DefaultLocalLlmPort;
        }

        string workMode = Environment.GetEnvironmentVariable("MARVIS_AGENT_WRAPPER_WORK_MODE");
        if (String.IsNullOrWhiteSpace(workMode))
        {
            workMode = "local";
        }

        string logPath = Environment.GetEnvironmentVariable("MARVIS_AGENT_WRAPPER_LOG");
        if (String.IsNullOrWhiteSpace(logPath))
        {
            logPath = Path.Combine(agentDir, "MarvisAgent.wrapper.log");
        }

        try
        {
            if (!File.Exists(realExe))
            {
                AppendLog(logPath, "missing real exe: " + realExe);
                return 1;
            }

            List<string> rewritten = RewriteArguments(args, workMode, localPort);
            string argumentLine = JoinArguments(rewritten);
            AppendLog(logPath, "launch \"" + realExe + "\" " + argumentLine);

            ProcessStartInfo startInfo = new ProcessStartInfo();
            startInfo.FileName = realExe;
            startInfo.Arguments = argumentLine;
            startInfo.WorkingDirectory = Path.GetDirectoryName(realExe);
            startInfo.UseShellExecute = false;
            startInfo.CreateNoWindow = true;

            using (Process child = Process.Start(startInfo))
            {
                child.WaitForExit();
                AppendLog(logPath, "exit code=" + child.ExitCode);
                return child.ExitCode;
            }
        }
        catch (Exception ex)
        {
            AppendLog(logPath, "error " + ex);
            return 1;
        }
    }

    private static List<string> RewriteArguments(string[] args, string workMode, int localPort)
    {
        List<string> rewritten = new List<string>();
        bool workModeSeen = false;
        bool localPortSeen = false;

        for (int i = 0; i < args.Length; i++)
        {
            string arg = args[i];

            if (arg == "--work_mode")
            {
                rewritten.Add(arg);
                rewritten.Add(workMode);
                workModeSeen = true;
                if (i + 1 < args.Length)
                {
                    i++;
                }
                continue;
            }

            if (arg.StartsWith("--work_mode=", StringComparison.Ordinal))
            {
                rewritten.Add("--work_mode=" + workMode);
                workModeSeen = true;
                continue;
            }

            if (arg == "--local_llm_port")
            {
                rewritten.Add(arg);
                rewritten.Add(localPort.ToString());
                localPortSeen = true;
                if (i + 1 < args.Length)
                {
                    i++;
                }
                continue;
            }

            if (arg.StartsWith("--local_llm_port=", StringComparison.Ordinal))
            {
                rewritten.Add("--local_llm_port=" + localPort);
                localPortSeen = true;
                continue;
            }

            rewritten.Add(arg);
        }

        if (!workModeSeen)
        {
            rewritten.Add("--work_mode");
            rewritten.Add(workMode);
        }
        if (!localPortSeen)
        {
            rewritten.Add("--local_llm_port");
            rewritten.Add(localPort.ToString());
        }

        return rewritten;
    }

    private static string JoinArguments(IEnumerable<string> args)
    {
        List<string> escaped = new List<string>();
        foreach (string arg in args)
        {
            escaped.Add(QuoteArgument(arg));
        }
        return String.Join(" ", escaped.ToArray());
    }

    private static string QuoteArgument(string arg)
    {
        if (arg.Length == 0)
        {
            return "\"\"";
        }

        bool needsQuotes = arg.IndexOfAny(new char[] { ' ', '\t', '"' }) >= 0;
        if (!needsQuotes)
        {
            return arg;
        }

        StringBuilder builder = new StringBuilder();
        builder.Append('"');
        int backslashCount = 0;
        foreach (char c in arg)
        {
            if (c == '\\')
            {
                backslashCount++;
                continue;
            }
            if (c == '"')
            {
                builder.Append('\\', backslashCount * 2 + 1);
                builder.Append('"');
                backslashCount = 0;
                continue;
            }
            builder.Append('\\', backslashCount);
            backslashCount = 0;
            builder.Append(c);
        }
        builder.Append('\\', backslashCount * 2);
        builder.Append('"');
        return builder.ToString();
    }

    private static void AppendLog(string logPath, string message)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(logPath));
        File.AppendAllText(
            logPath,
            DateTime.UtcNow.ToString("o") + " " + message + Environment.NewLine,
            Encoding.UTF8
        );
    }
}
