namespace Joytalk;

public class GameItem
{
	public string id { get; set; }

	public string name { get; set; }

	public int wear { get; set; }

	public int type { get; set; }

	public long price { get; set; }

	public int qualityMax { get; set; }

	public int quality { get; set; }

	public int hit { get; set; }

	public string fileName { get; set; }

	public int fileNum { get; set; }

	public int idx { get; set; }

	public int idxs { get; set; }

	public int num { get; set; }

	public int code { get; set; }

	public string detail { get; set; }

	public long user { get; set; }

	public bool happycity { get; set; }

	public string mapType { get; set; }

	public long bn { get; set; }

	public int hp { get; set; }

	public int exp { get; set; }

	public int cnt { get; set; }

	public bool merge { get; set; }

	public string state { get; set; }

	public int img { get; set; }

	public int fuel { get; set; }

	public string description { get; set; }

	public object Clone()
	{
		return MemberwiseClone();
	}
}
