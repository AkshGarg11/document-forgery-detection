import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { network } from "hardhat";

describe("DocumentVerification", async function () {
  const { viem } = await network.connect();

  it("issues and verifies a document", async function () {
    const contract = await viem.deployContract("DocumentVerification");

    const fileHash = ("0x" + "11".repeat(32)) as `0x${string}`;
    const textHash = ("0x" + "22".repeat(32)) as `0x${string}`;

    await contract.write.issueDocument([fileHash, textHash]);
    const result = (await contract.read.verifyDocument([fileHash])) as [
      boolean,
      bigint,
      `0x${string}`,
      boolean,
    ];

    assert.equal(result[0], true);
    assert.equal(result[2].toLowerCase().startsWith("0x"), true);
    assert.equal(result[3], false);
  });

  it("revokes an issued document", async function () {
    const contract = await viem.deployContract("DocumentVerification");

    const fileHash = ("0x" + "33".repeat(32)) as `0x${string}`;
    const textHash = ("0x" + "44".repeat(32)) as `0x${string}`;

    await contract.write.issueDocument([fileHash, textHash]);
    await contract.write.revokeDocument([fileHash]);

    const result = (await contract.read.verifyDocument([fileHash])) as [
      boolean,
      bigint,
      `0x${string}`,
      boolean,
    ];
    assert.equal(result[0], false);
    assert.equal(result[3], true);
  });

  it("rejects duplicate issue", async function () {
    const contract = await viem.deployContract("DocumentVerification");

    const fileHash = ("0x" + "55".repeat(32)) as `0x${string}`;
    const textHash = ("0x" + "66".repeat(32)) as `0x${string}`;

    await contract.write.issueDocument([fileHash, textHash]);

    await assert.rejects(async () => {
      await contract.write.issueDocument([fileHash, textHash]);
    });
  });
});
