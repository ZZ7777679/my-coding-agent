using System;
using System.IO;
using System.Net.Sockets;
using System.Threading.Tasks;

// 在服务所属 AppContainer 内转发固定端点，宿主仅通过继承管道交换字节。
// Relay one fixed endpoint inside the service AppContainer through inherited pipes.
internal static class SandboxBridge
{
    // 双向复制支持 HTTP、流式响应和 WebSocket，不解析或改写应用协议。
    // Copy both directions without interpreting HTTP, streaming or WebSocket payloads.
    private static int Main(string[] args)
    {
        try
        {
            using (var client = new TcpClient())
            {
                client.Connect(args[0], int.Parse(args[1]));
                using (var stream = client.GetStream())
                {
                    Task.Run(() => {
                        try {
                            Console.OpenStandardInput().CopyTo(stream);
                            client.Client.Shutdown(SocketShutdown.Send);
                        } catch (IOException) { client.Close(); }
                          catch (SocketException) { client.Close(); }
                          catch (ObjectDisposedException) { /* Connection already ended. */ }
                    });
                    stream.CopyTo(Console.OpenStandardOutput());
                }
            }
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.GetType().Name + ": " + error.Message);
            return 1;
        }
    }
}
