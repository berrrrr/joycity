// JoyTalk 코드 실험 샌드박스
// 역컴파일한 코드를 여기서 붙여넣고 테스트할 수 있습니다.
//
// 실행: dotnet run
// 빌드: dotnet build

using System.Text;
using System.Text.Json;

Console.WriteLine("=== 문자열 복호화 테스트 ===");
StringDecryptor.Test();

Console.WriteLine("\n=== 패킷 직렬화 테스트 ===");
PacketTest.Run();

// ──────────────────────────────────────────────────────────────────────────────
// 게임 코드에서 추출한 클래스들
// ──────────────────────────────────────────────────────────────────────────────

// 게임의 문자열 복호화 로직 (_6 함수와 동일)
// decompiled/-PrivateImplementationDetails-...cs 에서 추출
static class StringDecryptor
{
    // XOR 알고리즘: byte ^ position ^ 0xAA
    public static string Decrypt(byte[] blob, int offset, int length)
    {
        byte[] decrypted = new byte[length];
        for (int i = 0; i < length; i++)
            decrypted[i] = (byte)(blob[offset + i] ^ (offset + i) ^ 0xAA);
        return Encoding.UTF8.GetString(decrypted);
    }

    public static void Test()
    {
        string blobPath = Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "string_blob.bin");
        if (!File.Exists(blobPath))
        {
            Console.WriteLine("  string_blob.bin 없음 — 먼저 실행:");
            Console.WriteLine("  python3 extract_blob.py");
            return;
        }
        byte[] blob = File.ReadAllBytes(blobPath);
        Console.WriteLine($"  블롭 크기: {blob.Length} bytes");
        Console.WriteLine($"  [0] offset=0   len=52 → {Decrypt(blob, 0,  52)}");
        Console.WriteLine($"  [1] offset=52  len=48 → {Decrypt(blob, 52, 48)}");
        Console.WriteLine($"  [5] offset=234 len=23 → {Decrypt(blob, 234, 23)}");
    }
}

// 패킷 생성 테스트 — 실제 게임 코드와 동일한 방식
static class PacketTest
{
    // 한글을 이스케이프 없이 직렬화 (게임 코드와 동일)
    static readonly JsonSerializerOptions KoreanOptions = new()
    {
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.Create(
            System.Text.Unicode.UnicodeRanges.BasicLatin,
            System.Text.Unicode.UnicodeRanges.HangulSyllables
        )
    };

    public static void Run()
    {
        Packet("login",   new() { ["version"]="2.1.0", ["userid"]="test", ["userpw"]="1234" });
        Packet("move",    new() { ["no"]="1001", ["TX"]="450", ["TY"]="320" });
        Packet("chat",    new() { ["text"]="안녕하세요!" });
        Packet("webtoken", new());
    }

    static void Packet(string type, Dictionary<string, string> fields)
    {
        fields["type"] = type;
        Console.WriteLine($"  {type,-12} → {JsonSerializer.Serialize(fields, KoreanOptions)}");
    }
}
