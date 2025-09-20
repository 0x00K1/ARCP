# Changelog

All notable changes to this project will be documented in this file.

Patch versions are not included.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.x.x] [Unreleased]

### Planned
- **Full Database Integration**: Complete SQL migration with Alembic
- **CLI Interface**: Full-featured command-line interface with typer
- **Enhanced Logging**: Structured logging with correlation IDs and distributed tracing
- **Enhanced Configuration**: Dynamic configuration updates and environment-specific overrides
- **Advanced Dashboard**: Real-time monitoring with agent management, performance analytics, and resource optimization
- **Agent Banning System**: Automatic and manual agent blocking with reputation-based scoring
- **MyPy Integration**: Full static type checking with strict mode enabled
- **Enhanced Vector Search**: Improved embedding search with custom models and semantic filtering
- **Advanced Security**: Zero-trust architecture with enhanced threat detection and automated response

## [2.2.x] [Unreleased]

### Planned
- **Agent Marketplace**: Public agent registry with discovery, ratings, and deployment
- **Multi-Model Support**: Support for various AI models (OpenAI, Anthropic, local models)
- **Automated Registration**: Self-service agent onboarding with automated compliance validation
- **Monetization Features**: Usage tracking, billing integration, and marketplace transactions
- **Enhanced Discovery**: Advanced search filters, categories, and recommendation engine
- **Enhanced Audit**: Comprehensive security event logging and monitoring

## [2.1.x] [Unreleased]

### Planned - Three-Phase Registration (TPR)
- **Enhanced Security**: Proof-of-Possession tokens with DPoP and mTLS support
- **Agent Validation**: Asynchronous compliance and security checks before registration
- **Single-Use Tokens**: Atomic token consumption preventing replay attacks
- **Instance Tracking**: Multi-instance agent support with individual liveness monitoring
- **Improved AuthN/AuthZ**: Hierarchical token system (temp → validated → access)
- **Idempotency Support**: Safe retry mechanisms with correlation IDs

## [2.0.0] - 2025-08-18

### Added
- **Production-Ready Architecture**: Complete FastAPI-based microservices platform
- **Intelligent Agent Discovery**: Vector-based semantic search using Azure OpenAI embeddings
- **Enterprise Security**: Multi-tier authentication (PUBLIC/AGENT/ADMIN/ADMIN_PIN) with JWT tokens
- **Comprehensive API**: RESTful and WebSocket APIs with OpenAPI documentation
- **Python Client Library**: Full-featured async client with retry logic and error handling
- **Real-time Communication**: WebSocket support for live updates and agent communication
- **Advanced Monitoring**: Prometheus metrics, Grafana dashboards, and Jaeger tracing
- **Redis Integration**: High-performance caching with fallback to in-memory storage
- **Docker-Ready Deployment**: Complete Docker Compose stack with monitoring services
- **Comprehensive Testing**: Unit, integration, E2E, performance, and security test suites
- **Extensive Documentation**: Complete user guides, API reference, and deployment instructions
- **RFC-7807 Errors**: Standardized problem details for better error handling

### Security
- **Rate Limiting**: Built-in protection against abuse and DoS attacks
- **IP Filtering**: Configurable IP allow/deny lists with geolocation support
- **Content Filtering**: XSS protection and input sanitization
- **Session Management**: Secure session handling with timeout and binding
- **Audit Logging**: Comprehensive security event tracking and monitoring

### Performance
- **Vector Search**: Efficient agent discovery with embedding-based matching
- **Connection Pooling**: Optimized HTTP client with connection reuse
- **Background Processing**: Async task processing with proper resource management
- **Metrics Collection**: Real-time performance monitoring and alerting

### Developer Experience
- **Code Quality**: Black formatting, isort, flake8, and pre-commit hooks
- **Type Safety**: Comprehensive type annotations with pydantic models
- **Error Handling**: Structured exceptions with proper HTTP status codes

## [1.x.x] - 2025-03-20

### Added
- Initial release of ARCP
- Basic agent registration and discovery
- Simple HTTP API
- In-memory storage
- Basic configuration management
- Docker support
- Initial documentation

---

**Note**: This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
- **Major** version increments indicate breaking changes
- **Minor** version increments indicate new features
- **Patch** version increments indicate bug fixes

For migration guides and upgrade instructions, see the [Documentation](https://arcp.0x001.tech/docs).