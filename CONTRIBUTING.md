# Contributing to ARCP

Thank you for your interest in contributing to ARCP (Agent Registry & Control Protocol)! This document provides guidelines and information for contributors.

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Getting Started](#getting-started)
3. [Development Setup](#development-setup)
4. [Contributing Guidelines](#contributing-guidelines)
5. [Code Style and Standards](#code-style-and-standards)
6. [Testing](#testing)
7. [Documentation](#documentation)
8. [Pull Request Process](#pull-request-process)
9. [Release Process](#release-process)
10. [Community](#community)

## Code of Conduct

This project adheres to the [Apache Code of Conduct](https://www.apache.org/foundation/policies/conduct.html). By participating, you are expected to uphold this code.

## Getting Started

### Prerequisites

- **Python**: 3.11+ required
- **Docker**: For running the complete stack
- **Git**: For version control

### Quick Start

1. **Fork and clone the repository**:
   ```bash
   git clone https://github.com/0x00K1/ARCP.git
   cd ARCP
   ```

2. **Set up development environment**:
   ```bash
   # Install Poetry (if not already installed)
   curl -sSL https://install.python-poetry.org | python3 -

   # Install dependencies
   poetry install --with dev

   # Activate virtual environment
   poetry shell
   ```

3. **Set up environment variables**:
   ```bash
   cp .env.example .env
   cp .env deployment/docker/.env 
   # Edit .env with your configuration
   ```

4. **Run the development stack**:
   ```bash
   docker-compose -f deployment/docker/docker-compose.yml up -d
   ```

## Development Setup

### Local Development

1. **Install pre-commit hooks**:
   ```bash
   pre-commit install
   ```

2. **Run ARCP in development mode**:
   ```bash
   python -m arcp --host 0.0.0.0 --port 8001 --debug
   ```

### Project Structure

```
ARCP/
├── src/arcp/                 # Main application code
│   ├── api/                  # API endpoints
│   ├── core/                 # Core services and configuration
│   ├── models/               # Pydantic models
│   ├── services/             # External service integrations
│   └── utils/                # Utility functions
├── tests/                    # Test suite
│   ├── unit/                 # Unit tests
│   ├── integration/          # Integration tests
│   ├── e2e/                  # End-to-end tests
│   ├── fixtures/             # Test fixtures
│   ├── performance/          # Performance tests
│   └── security/             # Security tests
├── docs/                     # Documentation
├── examples/                 # Example agents and clients
├── deployment/               # Deployment configurations
└── monitoring/               # Monitoring configurations
```

## Contributing Guidelines

### Types of Contributions

We welcome the following types of contributions:

- **🐛 Bug Fixes**: Fix issues and improve stability
- **✨ New Features**: Add new functionality
- **📚 Documentation**: Improve or add documentation
- **🚀 Performance**: Optimize performance
- **🛡️ Security**: Enhance security measures
- **🧪 Tests**: Add or improve tests
- **♻️ Refactoring**: Improve code quality

### Before You Start

1. **Check existing issues** to avoid duplicate work
2. **Create an issue** to discuss major changes
3. **Join our discussions** for feature planning
4. **Review the roadmap** to align with project direction

## Code Style and Standards

### Python Code Style

We use strict code formatting and linting:

```bash
# Format code
poetry run black src/ tests/
poetry run isort src/ tests/

# Lint code
poetry run flake8 src/ tests/

# Packeges security scan
poetry run safety scan --output screen
```

### Code Standards

- **Type Hints**: All functions must have type hints
- **Documentation**: All public functions need docstrings
- **Error Handling**: Use structured exceptions
- **Logging**: Use structured logging with correlation IDs
- **Security**: Follow OWASP guidelines

### Configuration

All code style is configured in:
- `pyproject.toml`

## Testing

### Test Suite Structure

```bash
# Run all tests
pytest

# Run specific test types
pytest tests/unit/           # Unit tests
pytest tests/integration/    # Integration tests
pytest tests/e2e/           # End-to-end tests
pytest tests/performance/   # Performance tests
pytest tests/security/      # Security tests

# Run with coverage
pytest --cov=arcp --cov-report=html
```

### Writing Tests

1. **Unit Tests**: Test individual functions and classes
2. **Integration Tests**: Test service interactions
3. **E2E Tests**: Test complete workflows
4. **Performance Tests**: Test performance characteristics
5. **Security Tests**: Test security vulnerabilities

### Test Requirements

- **Coverage**: Maintain >90% test coverage
- **Async Support**: Use `pytest-asyncio` for async tests
- **Mocking**: Use `pytest-mock` for external dependencies
- **Fixtures**: Use fixtures for common test setup

## Documentation

### Types of Documentation

1. **API Documentation**: Auto-generated from code
2. **User Guides**: Step-by-step instructions
3. **Developer Guides**: Technical implementation details
4. **Deployment Guides**: Production setup instructions

### Documentation Standards

- **Markdown**: Use Markdown for all documentation
- **MkDocs**: Documentation is built with MkDocs Material
- **Code Examples**: Include working examples
- **Screenshots**: Add screenshots for UI components

## Pull Request Process

### Before Submitting

1. **Update tests**: Ensure tests pass and add new tests
2. **Update documentation**: Update relevant documentation
3. **Sync with main**: Rebase on latest main branch

### PR Requirements

- **Clear title**: Descriptive title summarizing changes
- **Detailed description**: Explain what, why, and how
- **Link issues**: Reference related issues
- **Breaking changes**: Clearly mark breaking changes
- **Testing**: Describe testing performed

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing performed

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No breaking changes (or clearly documented)
```

### Review Process

1. **Automated checks**: All CI checks must pass
2. **Code review**: At least one maintainer review
3. **Testing**: Comprehensive testing validation
4. **Documentation**: Documentation review if applicable

## Release Process

### Semantic Versioning

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (X.0.0): Breaking changes
- **MINOR** (0.X.0): New features (backward compatible)
- **PATCH** (0.0.X): Bug fixes (backward compatible)

### Release Workflow

1. **Feature freeze**: No new features during release preparation
2. **Testing**: Comprehensive testing of release candidate
3. **Documentation**: Update changelog and documentation
4. **Tagging**: Create release tag with proper version
5. **Deployment**: Deploy to staging, then production

## Community

### Getting Help

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: Community discussions and Q&A
- **Documentation**: Comprehensive guides and API reference

### Communication Guidelines

- **Be respectful**: Treat everyone with respect
- **Be constructive**: Provide actionable feedback
- **Be patient**: Maintainers are volunteers
- **Search first**: Check existing issues and discussions

### Maintainer Responsibilities

Maintainers are responsible for:
- **Code review**: Thorough review of contributions
- **Issue triage**: Categorizing and prioritizing issues
- **Release management**: Coordinating releases
- **Community management**: Fostering a welcoming community

## Recognition

Contributors are recognized through:
- **Contributors file**: All contributors listed
- **Release notes**: Contributor acknowledgments
- **GitHub insights**: Contribution statistics
- **Community highlights**: Outstanding contributions featured

---

## Questions?

If you have questions about contributing, please:

1. Check the [documentation](https://arcp.0x001.tech/docs)
2. Search [existing issues](https://github.com/0x00K1/ARCP/issues)
3. Start a [discussion](https://github.com/0x00K1/ARCP/discussions)
4. Contact maintainers directly

Thank you for contributing to ARCP! 🚀