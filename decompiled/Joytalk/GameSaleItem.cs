namespace Joytalk;

public class GameSaleItem : GameItem
{
	public string saleId { get; set; }

	public long saleNo { get; set; }

	public long salePrice { get; set; }

	public long salePoint { get; set; }

	public int order { get; set; }

	public int count { get; set; }

	public new object Clone()
	{
		return MemberwiseClone();
	}
}
