#!/usr/bin/env python3
"""Test Damodaran persistent file caching."""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.external.damodaran import get_damodaran_loader


def test_cache_persistence():
    """Test that Damodaran cache persists across instances."""
    print("=" * 70)
    print("Testing Damodaran Persistent File Cache")
    print("=" * 70)
    
    # First instance - may download data
    print("\n📦 Creating first loader instance...")
    loader1 = get_damodaran_loader()
    
    print("\n📊 Checking cache status...")
    status1 = loader1.get_cache_status()
    print(f"   Status: {status1['status']}")
    print(f"   Cache location: {status1['cache_location']}")
    
    # Fetch sector priors (triggers download if needed)
    print("\n🔍 Fetching Technology sector priors...")
    start_time = time.time()
    tech_priors = loader1.get_sector_priors("Technology")
    elapsed1 = time.time() - start_time
    
    print(f"\n   ✅ Retrieved in {elapsed1:.2f} seconds")
    print(f"   Beta: {tech_priors.beta}")
    print(f"   Revenue Growth: {tech_priors.revenue_growth:.1%}")
    print(f"   Operating Margin: {tech_priors.operating_margin:.1%}")
    
    # Check cache status after fetch
    print("\n📊 Cache status after fetch:")
    status2 = loader1.get_cache_status()
    print(f"   Status: {status2['status']}")
    print(f"   Age: {status2['age_days']} days")
    print(f"   Expires in: {status2['expires_in_days']} days")
    print(f"   Beta cached: {status2['beta_cached']}")
    print(f"   Margin cached: {status2['margin_cached']}")
    
    # Simulate new process - create fresh instance
    print("\n🔄 Simulating new Python process (creating fresh loader)...")
    print("   (This would be a separate terminal/program run)")
    
    # Reset singleton to simulate new process
    import src.external.damodaran as dam_module
    dam_module._global_loader = None
    
    # Second instance - should load from disk cache
    print("\n📦 Creating second loader instance...")
    loader2 = get_damodaran_loader()
    
    print("\n🔍 Fetching Technology sector priors again...")
    start_time = time.time()
    tech_priors2 = loader2.get_sector_priors("Technology")
    elapsed2 = time.time() - start_time
    
    print(f"\n   ✅ Retrieved in {elapsed2:.2f} seconds")
    print(f"   Beta: {tech_priors2.beta}")
    
    # Compare performance
    print("\n" + "=" * 70)
    print("Performance Comparison:")
    print("=" * 70)
    print(f"   First fetch:  {elapsed1:.2f} seconds")
    print(f"   Second fetch: {elapsed2:.2f} seconds")
    
    if elapsed2 < elapsed1:
        speedup = (elapsed1 - elapsed2) / elapsed1 * 100
        print(f"   ⚡ {speedup:.0f}% faster using persistent cache!")
    
    # Test multiple sectors
    print("\n" + "=" * 70)
    print("Testing Multiple Sectors:")
    print("=" * 70)
    
    sectors = ["Healthcare", "Financial Services", "Energy"]
    for sector in sectors:
        priors = loader2.get_sector_priors(sector)
        print(f"\n   {sector}:")
        print(f"      Beta: {priors.beta}")
        print(f"      Growth: {priors.revenue_growth:.1%}")
    
    print("\n" + "=" * 70)
    print("✅ Cache persistence test completed successfully!")
    print("=" * 70)
    print("\n💡 Key takeaways:")
    print("   • Cache is saved to: data/cache/damodaran/")
    print("   • Persists across program runs")
    print("   • Valid for 30 days")
    print("   • Significantly faster subsequent loads")


def test_cache_status_command():
    """Test cache status reporting."""
    print("\n" + "=" * 70)
    print("Testing Cache Status Command")
    print("=" * 70)
    
    loader = get_damodaran_loader()
    status = loader.get_cache_status()
    
    print(f"\n📊 Damodaran Cache Status:")
    print(f"   Status: {status['status'].upper()}")
    
    if status['status'] != 'empty':
        print(f"   Last Updated: {status['timestamp']}")
        print(f"   Age: {status['age_days']} days old")
        print(f"   Expires In: {status['expires_in_days']} days")
        print(f"   Cache Period: {status['cache_days']} days")
        print(f"   Beta Dataset: {'✅ Cached' if status['beta_cached'] else '❌ Missing'}")
        print(f"   Margin Dataset: {'✅ Cached' if status['margin_cached'] else '❌ Missing'}")
        print(f"   Location: {status['cache_location']}")
    else:
        print(f"   {status['message']}")


if __name__ == "__main__":
    try:
        test_cache_persistence()
        test_cache_status_command()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
