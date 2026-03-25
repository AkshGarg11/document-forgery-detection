/**
 * blockchain/scripts/deploy.js
 * Deploys DocumentVerification contract using Hardhat / ethers.js.
 *
 * Usage:
 *   npx hardhat run scripts/deploy.js --network localhost
 *   npx hardhat run scripts/deploy.js --network sepolia
 */

const { ethers } = require("hardhat");

async function main() {
  const [deployer] = await ethers.getSigners();

  console.log("=================================================");
  console.log("Deploying DocumentVerification contract...");
  console.log("Deployer address:", deployer.address);
  console.log(
    "Account balance:",
    (await deployer.provider.getBalance(deployer.address)).toString()
  );
  console.log("=================================================");

  // Compile & deploy
  const DocumentVerification = await ethers.getContractFactory(
    "DocumentVerification"
  );
  const contract = await DocumentVerification.deploy();
  await contract.waitForDeployment();

  const address = await contract.getAddress();

  console.log("✅ DocumentVerification deployed at:", address);
  console.log("=================================================");
  console.log("Add this to your .env:");
  console.log(`CONTRACT_ADDRESS=${address}`);
  console.log("=================================================");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error("Deployment failed:", error);
    process.exit(1);
  });
