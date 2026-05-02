using System.Collections.Generic;

namespace Joytalk;

public class GameObject
{
	public int SortY;

	public long no { get; set; }

	public string id { get; set; }

	public string name { get; set; }

	public long handle { get; set; }

	public int level { get; set; }

	public string type { get; set; }

	public string itemFilename { get; set; }

	public string mapid { get; set; }

	public int idx { get; set; }

	public int idxs { get; set; }

	public int OX { get; set; }

	public int OY { get; set; }

	public int DX { get; set; }

	public int DY { get; set; }

	public int PX { get; set; }

	public int PY { get; set; }

	public int RX { get; set; }

	public int RY { get; set; }

	public uint TX { get; set; }

	public uint TY { get; set; }

	public int VX { get; set; }

	public int VY { get; set; }

	public int SX { get; set; }

	public int SY { get; set; }

	public int speed { get; set; }

	public int EY { get; set; }

	public int EOY { get; set; }

	public int ClickEvent { get; set; }

	public string saleId { get; set; }

	public string Chat { get; set; }

	public int ChatTime { get; set; }

	public int[] chatColor { get; set; } = new int[3];

	public string TypingText { get; set; }

	public int TypingTime { get; set; }

	public int animationCount { get; set; }

	public int defaultAni { get; set; }

	public int[] preorder { get; set; } = new int[20];

	public Dictionary<int, ItemColorTable> itemColor { get; set; } = new Dictionary<int, ItemColorTable>();

	public bool[] itemColord { get; set; } = new bool[20];

	public long timeStamp { get; set; }

	public long oldTimeStamp { get; set; }

	public int drawtype { get; set; }

	public bool happycity { get; set; }

	public int stateIdx { get; set; }

	public int stateIdxs { get; set; }

	public int colorVariant { get; set; }

	public object Clone()
	{
		return MemberwiseClone();
	}
}
