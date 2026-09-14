"""Contract-first crypto identity and exchange-qualified equity identity."""

import unittest

from terminal import identity


class IdentityTests(unittest.TestCase):
    def test_equity_canonical_form(self):
        asset = identity.equity("exa", "xnas")
        self.assertEqual(asset.canonical, "eq:XNAS:EXA")
        self.assertEqual(identity.validate(asset), [])

    def test_evm_contract_is_lower_cased_and_base58_is_not(self):
        mixed_case = "0xABCDEFabcdef0123456789ABCDEFabcdef012345"
        evm = identity.crypto("TKN", "pulsechain", mixed_case)
        self.assertEqual(evm.canonical, "cx:pulsechain:" + mixed_case.lower())
        self.assertEqual(identity.validate(evm), [])
        sol = identity.crypto("MOCK", "solana", "SyntheticMintAddress111111111111111111111111")
        self.assertEqual(sol.key, "SyntheticMintAddress111111111111111111111111")
        self.assertEqual(identity.validate(sol), [])

    def test_validation_catches_bad_shapes(self):
        self.assertTrue(identity.validate(identity.AssetId("equity", "X", "NASDAQ", "X")))
        self.assertTrue(identity.validate(identity.AssetId("equity", "1AB", "XNAS", "1AB")))
        self.assertTrue(identity.validate(identity.AssetId("crypto", "T", "pulsechain", "0x1234")))
        self.assertTrue(
            identity.validate(
                identity.AssetId(
                    "crypto", "T", "pulsechain", "0xABCDEFabcdef0123456789ABCDEFabcdef012345"
                )
            )
        )
        self.assertTrue(identity.validate(identity.AssetId("crypto", "T", "solana", "0xabc")))
        self.assertTrue(identity.validate(identity.AssetId("crypto", "", "bitcoin", "native")))
        self.assertTrue(identity.validate(identity.AssetId("option", "EXA", "XCBO", "not-occ")))
        self.assertTrue(identity.validate(identity.AssetId("bond", "X", "Y", "Z")))

    def test_native_asset_needs_no_contract(self):
        btc = identity.crypto("BTC", "bitcoin")
        self.assertEqual(btc.canonical, "cx:bitcoin:native")
        self.assertEqual(identity.validate(btc), [])

    def test_parse_round_trips_and_rejects_junk(self):
        asset = identity.parse("cx:pulsechain:0xABCDEFabcdef0123456789ABCDEFabcdef012345", "TKN")
        self.assertEqual(
            asset.canonical, "cx:pulsechain:0xabcdefabcdef0123456789abcdefabcdef012345"
        )
        self.assertEqual(identity.parse("eq:XNYS:EXB").symbol, "EXB")
        with self.assertRaises(ValueError):
            identity.parse("EXA")
        with self.assertRaises(ValueError):
            identity.parse("zz:XNAS:EXA")

    def test_symbol_collisions_are_reported(self):
        assets = [
            identity.crypto("MAX", "solana", "SyntheticMintAddress111111111111111111111111"),
            identity.crypto("max", "bsc", "0x000000000000000000000000000000000000abcd"),
            identity.equity("MAX", "XNAS"),
            identity.equity("EXA", "XNAS"),
        ]
        collisions = identity.collisions(assets)
        self.assertEqual(set(collisions), {"MAX"})
        self.assertEqual(len(collisions["MAX"]), 3)


if __name__ == "__main__":
    unittest.main()
