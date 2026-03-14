using Serilog;

namespace WinNativeApp;

static class Program
{
    [STAThread]
    static void Main(string[] args)
    {
        var logDir = Path.Combine(AppContext.BaseDirectory, "logs");
        Directory.CreateDirectory(logDir);

        Log.Logger = new LoggerConfiguration()
            .MinimumLevel.Debug()
            .WriteTo.Console(
                outputTemplate: "{Timestamp:HH:mm:ss.fff} [{Level:u3}] {Message:lj}{NewLine}{Exception}")
            .WriteTo.File(
                Path.Combine(logDir, "app.log"),
                rollingInterval: RollingInterval.Day,
                retainedFileCountLimit: 7,
                outputTemplate: "{Timestamp:HH:mm:ss.fff} [{Level:u3}] {Message:lj}{NewLine}{Exception}")
            .CreateLogger();

        Log.Information("WinNativeApp starting...");

        try
        {
            ApplicationConfiguration.Initialize();
            Application.Run(new MainForm(args));
        }
        catch (Exception ex)
        {
            Log.Fatal(ex, "Application crashed");
        }
        finally
        {
            Log.CloseAndFlush();
        }
    }
}
