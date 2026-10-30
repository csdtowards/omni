# Yuan Liu

Email: liuyuanvic@gmail.com | Phone: (+86) 18550017589

## Professional Summary

Backend and distributed systems engineer with experience in blockchain infrastructure, trading systems, AI applications, and developer productivity platforms. Built systems from the ground up and served as a team technical lead, with responsibilities spanning requirements analysis, architecture, core development, code review, and production support.

## Technical Skills

- System Design: Backend architecture, distributed systems, data consistency, fault recovery, blockchain infrastructure, performance optimization.
- Languages: Rust, Python, Go, C++, Java, Solidity.
- Data Infrastructure: NoSQL, PostgreSQL, Kafka, Redpanda, Redis, Hadoop.
- Engineering: Familiar with gRPC, Docker, Kubernetes, Prometheus, and CI/CD.
- Continuous Learning: ongoing learning in AI, LLMs, LangGraph workflows and agents.

## Professional Experience

### Conflux | Sep 2021 - Present | Technical Expert / Software Engineer

- **Perp DEX (Fully On-chain Perpetuals)**: Built the off-chain backend from scratch using Rust, Tokio, and Axum, covering on-chain event indexing, state projection, transaction forwarding, oracle services, and REST/WebSocket APIs while supporting consistency and low latency for high-frequency trading. Implemented idempotent processing, state replay, and chain-reorganization rollback using Redpanda transactional messaging, PostgreSQL WAL, and snapshots; optimized synchronization and recovery through tiered storage and separate real-time and historical read paths.
- **0G Compute (Fine-tuning / Inference / AI Verse)**: Contributed to inference and fine-tuning services. Refactored fine-tuning task preparation, execution, and result handling, implementing worker-pool concurrency and task queues with support for timeout retries, CPU/GPU/memory quotas, custom model configuration, and containerized execution.
- **0G Chat (AI Chat Application)**: Contributed to the backend, integrating Flux and Playground text-to-image models through a unified asynchronous interface and LangGraph workflows, and improving storage of generated outputs. Developed on-chain subscription contracts and backend services for tiered entitlements and subscription status queries.
- **Cross-chain Bridge (Smart Contracts & Backend Services)**: Led bridge design, development, and maintenance across smart contracts and backend services, improving transaction state transitions and error handling. Optimized Fast Path confirmation logic, with Fast Path cross-chain transfers completing in under one minute, enhance the cross-chain experience for user assets significantly.
- **Public & Consortium Blockchains**: Developed and maintained consensus and storage modules for consortium and public Conflux blockchains, delivering enhancements and troubleshooting issues. Optimized storage to address data redundancy and synchronization bottlenecks, reducing snapshot creation time by 60%.
- **Decentralized Storage / DA**: Developed and maintained synchronization modules and the DA client for decentralized storage and data availability systems; improved synchronization logic and client interfaces and integrated with external systems.

### Microsoft | Jul 2013 - Sep 2021 | Tech Lead / Software Engineer

- **Automated Validation & Dependency Management Platform**: Led technical design, delivery, code reviews, and critical issue resolution as the EverGreen team's Tech Lead; promoted development practices, engineering standards, and knowledge sharing. Built a platform using Azure Service Bus and CI/CD to provide one-click validation for thousands of developers and automate validation, publishing, and updates for approximately 400 NuGet packages per day.
- **Cop / DeadCode Detection (Build Performance & Code Quality)**: Extended the Cop file-checking mechanism with online and offline modes, improving MSBuild performance by approximately 13%. Implemented DeadCode Detection using static and dynamic dependencies and call-stack sampling, removing approximately 10% of unused projects.
- **Focus (Functional Testing Platform)**: Re-architected the platform with multiple instances, sharding, and gRPC, supporting up to 100,000 test cases, approximately 20 million data entries, and approximately 2 million new logs daily. Migrated historical data to Cosmos for hot/cold separation; doubled dataset insertion performance and reduced page load time by 50% through caching and database optimizations. Calculated approximately 72% overall test-case stability from historical logs, pass rates, and similarity metrics.
- **Build Break Detector (Build Failure Diagnosis)**: Designed and developed Build Break Detector to identify commits responsible for build failures using error logs, code changes, and project dependencies. Re-architected the existing Redis/Kafka primary-replica system as a peer-to-peer system; in practice, the success rate of "Undo commit" is 100%, with a coverage of approximately 70%; achieved an overall detection success rate of approximately 88% and an average end-to-end detection time of approximately 37 minutes.
- **IE (Browser Settings Protection)**: Contributed to user-settings protection in Internet Explorer, including registry reads, browser plug-ins, API hooks, telemetry collection, and data analysis with Cosmos and Scope.

## Education

- University of Chinese Academy of Sciences / Institute of Software, Chinese Academy of Sciences | Master's degree (admitted by recommendation) | Sep 2010 - Jul 2013
- Chongqing University / School of Software | Bachelor's degree | Sep 2006 - Jul 2010
