# Use an official Node.js runtime as a parent image
FROM node:18-alpine

# Set the working directory in the container
WORKDIR /usr/src/app

# Copy package.json and package-lock.json to the working directory
COPY blockchain/package*.json ./

# Install any needed packages
RUN npm install

# Bundle app source
COPY blockchain/ .

# Make port 8545 available to the world outside this container
EXPOSE 8545

# Run the app when the container launches
CMD ["npx", "hardhat", "node", "--hostname", "0.0.0.0"]
