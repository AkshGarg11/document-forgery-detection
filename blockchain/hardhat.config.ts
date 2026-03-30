import hardhatToolboxViemPlugin from "@nomicfoundation/hardhat-toolbox-viem";
import { defineConfig } from "hardhat/config";

export default defineConfig({
  plugins: [hardhatToolboxViemPlugin],
  solidity: {
    profiles: {
      default: {
        version: "0.8.28",
        settings: {
          evmVersion: "paris",
        },
      },
      production: {
        version: "0.8.28",
        settings: {
          evmVersion: "paris",
          optimizer: {
            enabled: true,
            runs: 200,
          },
        },
      },
    },
  },
  networks: {
    hardhatMainnet: {
      type: "edr-simulated",
      chainType: "l1",
    },
    hardhatOp: {
      type: "edr-simulated",
      chainType: "op",
    },
    ganache: {
      type: "http",
      chainType: "l1",
      url: process.env.GANACHE_RPC_URL || "http://127.0.0.1:7545",
      accounts: process.env.GANACHE_PRIVATE_KEY
        ? [process.env.GANACHE_PRIVATE_KEY]
        : "remote",
    },
    ...(process.env.SEPOLIA_RPC_URL && process.env.SEPOLIA_PRIVATE_KEY
      ? {
          sepolia: {
            type: "http" as const,
            chainType: "l1" as const,
            url: process.env.SEPOLIA_RPC_URL,
            accounts: [process.env.SEPOLIA_PRIVATE_KEY],
          },
        }
      : {}),
  },
});
