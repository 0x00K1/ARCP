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

## [2.1.0] - 2026-02-16

### Added - Three-Phase Registration (TPR)
- **Three-Phase Registration Protocol**: Enhanced agent onboarding with validation pipeline
  - Phase 1: Temporary token issuance with rate limiting
  - Phase 2: Asynchronous compliance and security validation
  - Phase 3: Production token with cryptographic binding
- **DPoP Support (RFC 9449)**: Demonstrating Proof-of-Possession for token security
  - JWT-based proof generation and validation
  - JWK thumbprint binding (cnf claim)
  - Replay attack prevention with jti tracking
  - Token theft mitigation through cryptographic binding
- **mTLS Client Authentication**: Mutual TLS certificate-based authentication
  - X.509 client certificate validation
  - SPKI hash binding for token security
  - OCSP and CRL revocation checking
  - Certificate rotation support
- **SBOM Verification**: Software Bill of Materials vulnerability scanning
  - SPDX and CycloneDX format support
  - Real-time vulnerability checking via OSV database
  - Severity-based filtering and compliance verification
  - Automated dependency scanning
- **Container Security Scanning**: Image vulnerability detection
  - Trivy and Grype scanner integration
  - CVE database synchronization
  - Secret detection in container images
  - License compliance checking
- **Software Attestation**: Challenge-response integrity verification
  - Code and configuration measurement
  - Cryptographic signature validation
  - Periodic re-attestation support
  - Tamper detection capabilities
- **JWKS Management**: JSON Web Key Set for asymmetric signing
  - RS256/ES256 algorithm support
  - Automatic key rotation with configurable intervals
  - Multi-key support for graceful rollover
  - Public key distribution via /.well-known/jwks.json

### Security
- **Enhanced Token Security**: DPoP and mTLS binding preventing token theft
- **Zero-Trust Validation**: Comprehensive pre-registration security checks
- **Single-Use Tokens**: Atomic token consumption with replay protection
- **Instance Tracking**: Per-instance authentication and liveness monitoring
- **Asymmetric Cryptography**: JWKS-based token signing for enhanced security
- **Certificate Management**: Complete mTLS lifecycle with rotation support

### Infrastructure
- **NGINX Reverse Proxy**: Production-ready reverse proxy integration
  - TLS termination and client certificate validation
  - HTTP/2 support with WebSocket upgrade
  - Load balancing and connection pooling
  - Security header injection
- **Enhanced Docker Stack**: Complete containerized deployment
  - NGINX container with mTLS configuration
  - Certificate volume mounting
  - Network isolation and security
  - Production-ready compose configuration

### Documentation
- **Comprehensive Security Guides**: Complete documentation for all v2.1.0 features
  - Three-Phase Registration guide with flow diagrams
  - DPoP implementation guide with RFC 9449 compliance
  - mTLS setup and certificate management
  - SBOM verification and vulnerability scanning
  - Container security scanning integration
  - Software attestation implementation
  - JWKS management and key rotation
- **Mermaid Diagrams**: All documentation includes interactive flow diagrams
- **Configuration Examples**: Production-ready configuration templates
- **Troubleshooting Guides**: Common issues and solutions for each feature

### Developer Experience
- **Enhanced Client Examples**: DPoP and mTLS client implementations
- **Security Best Practices**: Comprehensive security guidelines
- **Migration Guides**: Upgrade path from v2.0.x to v2.1.0
- **API Extensions**: New TPR endpoints with OpenAPI documentation

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