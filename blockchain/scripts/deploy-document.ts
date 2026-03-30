import { network } from "hardhat";

const { viem } = await network.connect();
const contract = await viem.deployContract("DocumentVerification");

console.log("=================================================");
console.log("DocumentVerification deployed at:", contract.address);
console.log("Add this in backend .env:");
console.log(`CONTRACT_ADDRESS=${contract.address}`);
console.log("=================================================");
