const { Queue } = require("bullmq");
const IORedis = require("ioredis");
const config = require("./config");

const connection = new IORedis(config.redisUrl, { maxRetriesPerRequest: null });
const jobs = new Queue("jobs", { connection });
const deadLetters = new Queue("jobs-dlq", { connection });

const JOB_OPTIONS = { attempts: 3, backoff: { type: "fixed", delay: 200 }, removeOnComplete: 5000 };

async function enqueue(name, data, id) {
  await jobs.add(name, data, { ...JOB_OPTIONS, jobId: id });
}

module.exports = { connection, jobs, deadLetters, enqueue };
